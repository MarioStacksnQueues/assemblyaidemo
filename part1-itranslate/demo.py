"""
iTranslate STT demo for AssemblyAI Universal-3 Pro Streaming.

Simulates an iTranslate device by streaming laptop microphone audio
to AAI's cloud API and displaying live transcripts. Demonstrates the
six STT accuracy levers iTranslate's engineering team should tune
when integrating their handheld device.

Default run is STT-only. The --enable-translation and --enable-tts
flags add an optional full pipeline (GPT-4o-mini translate, ElevenLabs
Flash v2.5 TTS, sounddevice playback) for end-to-end demonstration.

Usage:
  python demo.py
  python demo.py --source-lang en --target-lang es
  python demo.py --keyterms keyterms.txt --enable-translation --enable-tts
"""

# ---------------------------------------------------------------------------
# STT ACCURACY LEVERS (the six knobs iTranslate's team should tune)
# ---------------------------------------------------------------------------
# 1. format_turns=true            Capitalization, punctuation, and turn-final
#                                 normalization on the server side. Highest-
#                                 ROI lever for human-readable transcripts.
# 2. keyterms_prompt              Per-session vocabulary boost (proper nouns,
#                                 product names, domain jargon). Loaded from
#                                 a flat file via --keyterms.
# 3. end_of_turn_confidence_threshold
#                                 How sure the server must be that a turn
#                                 ended before emitting a final. Trade-off:
#                                 lower = snappier finals, higher = fewer
#                                 mid-sentence cutoffs.
# 4. min_end_of_turn_silence_when_confident
#                                 Floor on silence required before finalizing
#                                 a confident turn. Tunes responsiveness.
# 5. max_turn_silence             Hard ceiling. Forces a finalize even when
#                                 the model is uncertain. Prevents stuck
#                                 partials on noisy mics.
# 6. sample_rate / chunk discipline
#                                 16 kHz PCM s16le, ~50 ms frames. Anything
#                                 jittery here costs WER. We pin both.
#
# Plus: speech_model=u3-rt-pro (REQUIRED, no default). Universal-3 Pro
# Streaming covers EN/ES/DE/FR/PT/IT with native code-switching, which is
# exactly what a handheld translator needs.
#
# Out of scope for this cloud demo but worth flagging to iTranslate:
# on-device preprocessing (AGC, noise suppression, VAD gating) before the
# bytes ever hit the WebSocket. The handheld's mic and DSP chain probably
# matter more than any server-side knob.
# ---------------------------------------------------------------------------

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import websockets
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed

# Audio constants. 16 kHz PCM s16le is what u3-rt-pro expects.
# 50 ms frames at 16 kHz = 800 samples = 1600 bytes. Small enough to keep
# end-to-end latency low, large enough to amortize WS framing overhead.
SAMPLE_RATE = 16_000
FRAME_MS = 50
FRAMES_PER_CHUNK = SAMPLE_RATE * FRAME_MS // 1000  # 800
BYTES_PER_CHUNK = FRAMES_PER_CHUNK * 2

# ANSI colors. Subtle markers so the partial vs final distinction is obvious
# during a live demo without depending on a TUI library.
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_CYAN = "\033[36m"
C_YELLOW = "\033[33m"
C_RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Config plumbing
# ---------------------------------------------------------------------------

@dataclass
class DemoConfig:
    """Runtime configuration assembled from CLI args plus environment."""
    source_lang: str
    target_lang: str
    keyterms: list[str]
    enable_translation: bool
    enable_tts: bool
    aai_key: str
    openai_key: str | None
    elevenlabs_key: str | None
    timings: dict[str, float] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    """Parse CLI flags. Defaults match a typical iTranslate device session."""
    p = argparse.ArgumentParser(
        description="iTranslate STT demo on AssemblyAI Universal-3 Pro Streaming.",
    )
    p.add_argument("--source-lang", default="en", help="Hint for input language (auto-detected anyway).")
    p.add_argument("--target-lang", default="es", help="Target language for translation pipeline.")
    p.add_argument("--keyterms", type=Path, default=None, help="Optional path to a keyterms file (one term per line).")
    p.add_argument("--enable-translation", action="store_true", help="Run GPT-4o-mini translation on each finalized turn.")
    p.add_argument("--enable-tts", action="store_true", help="Run ElevenLabs Flash v2.5 TTS and play through speakers.")
    return p.parse_args()


def load_config(args: argparse.Namespace) -> DemoConfig:
    """Validate env vars and load optional keyterms file."""
    load_dotenv()
    aai_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not aai_key:
        sys.exit("ERROR: ASSEMBLYAI_API_KEY missing. Copy .env.example to .env and fill it in.")

    openai_key = os.getenv("OPENAI_API_KEY")
    if args.enable_translation and not openai_key:
        sys.exit("ERROR: --enable-translation requires OPENAI_API_KEY in .env.")

    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    if args.enable_tts and not elevenlabs_key:
        sys.exit("ERROR: --enable-tts requires ELEVENLABS_API_KEY in .env.")
    if args.enable_tts and not args.enable_translation:
        sys.exit("ERROR: --enable-tts requires --enable-translation (TTS speaks the translated text).")

    keyterms: list[str] = []
    if args.keyterms:
        if not args.keyterms.exists():
            sys.exit(f"ERROR: keyterms file not found: {args.keyterms}")
        keyterms = [line.strip() for line in args.keyterms.read_text(encoding="utf-8").splitlines() if line.strip()]

    return DemoConfig(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        keyterms=keyterms,
        enable_translation=args.enable_translation,
        enable_tts=args.enable_tts,
        aai_key=aai_key,
        openai_key=openai_key,
        elevenlabs_key=elevenlabs_key,
    )


def build_aai_url(cfg: DemoConfig) -> str:
    """Compose the v3 streaming URL with all relevant accuracy levers wired up."""
    # speech_model=u3-rt-pro is required (no default on the v3 endpoint).
    # format_turns=true gives capitalization and punctuation on finals.
    # language_detection=true lets u3-rt-pro identify EN/ES/DE/FR/PT/IT live.
    params = [
        "sample_rate=16000",
        "speech_model=u3-rt-pro",
        "encoding=pcm_s16le",
        "format_turns=true",
        "language_detection=true",
    ]
    return "wss://streaming.assemblyai.com/v3/ws?" + "&".join(params)


# ---------------------------------------------------------------------------
# Mic capture
# ---------------------------------------------------------------------------

def pick_input_device() -> tuple[int, str]:
    """Resolve and log the default input device. Useful on Windows WASAPI."""
    info = sd.query_devices(kind="input")
    # query_devices(kind=...) returns a dict on a single match.
    name = info["name"] if isinstance(info, dict) else str(info)
    idx = sd.default.device[0] if sd.default.device[0] is not None else 0
    return idx, name


async def mic_capture(audio_q: asyncio.Queue[bytes], stop_evt: asyncio.Event) -> None:
    """Push 50 ms PCM s16le chunks from the default input device into audio_q.

    The sounddevice callback runs on a portaudio thread. We MUST NOT do work
    there; we only marshal bytes back to the asyncio loop via call_soon_threadsafe.
    """
    loop = asyncio.get_running_loop()
    device_idx, device_name = pick_input_device()
    print(f"{C_DIM}Microphone: {device_name} (idx {device_idx}){C_RESET}")

    def _callback(indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            # XRuns and overflows surface here. Log but never block.
            print(f"{C_YELLOW}[mic] {status}{C_RESET}", file=sys.stderr)
        # indata is int16 already because of dtype below. tobytes is a memcpy.
        loop.call_soon_threadsafe(audio_q.put_nowait, bytes(indata))

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAMES_PER_CHUNK,
        callback=_callback,
    )
    with stream:
        await stop_evt.wait()


# ---------------------------------------------------------------------------
# AssemblyAI WebSocket
# ---------------------------------------------------------------------------

async def aai_sender(ws: websockets.WebSocketClientProtocol, audio_q: asyncio.Queue[bytes], stop_evt: asyncio.Event) -> None:
    """Drain mic chunks from audio_q and forward them as binary WS frames."""
    while not stop_evt.is_set():
        try:
            chunk = await asyncio.wait_for(audio_q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        try:
            await ws.send(chunk)
        except ConnectionClosed:
            stop_evt.set()
            return


async def aai_receiver(
    ws: websockets.WebSocketClientProtocol,
    cfg: DemoConfig,
    translate_q: asyncio.Queue[str] | None,
    stop_evt: asyncio.Event,
) -> None:
    """Read JSON messages from AAI and surface partials, finals, and turns."""
    last_lang: str | None = None
    # Local wall-clock timer for the current turn. Reset to None after each
    # finalized turn so the next turn starts fresh on its first partial.
    turn_start_ts: float | None = None
    async for raw in ws:
        if stop_evt.is_set():
            break
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        mtype = msg.get("type")
        if mtype == "Begin":
            sid = msg.get("id", "?")
            print(f"{C_DIM}[session] Begin id={sid}{C_RESET}")
            continue

        if mtype == "Termination":
            print(f"{C_DIM}[session] Termination{C_RESET}")
            stop_evt.set()
            break

        if mtype == "Turn":
            text = (msg.get("transcript") or "").strip()
            if not text:
                continue

            # Surface detected language whenever it changes. u3-rt-pro flips
            # between EN/ES/DE/FR/PT/IT mid-conversation if code-switching
            # happens, which is exactly the iTranslate use case.
            lang = msg.get("language") or msg.get("detected_language")
            if lang and lang != last_lang:
                last_lang = lang
                print(f"\n{C_DIM}[LANG: {lang}]{C_RESET}")

            is_formatted = bool(msg.get("turn_is_formatted"))
            end_of_turn = bool(msg.get("end_of_turn"))

            if not end_of_turn:
                # Partial. Overwrite the same line. \r + clear-to-end-of-line.
                if turn_start_ts is None:
                    # First partial of a new turn. Start the wall-clock timer.
                    turn_start_ts = time.perf_counter()
                sys.stdout.write(f"\r\033[K{C_DIM}{text}{C_RESET}")
                sys.stdout.flush()
                continue

            # Finalized turn. Clear the partial line first, then commit.
            sys.stdout.write("\r\033[K")
            tag = "[TURN]" if is_formatted else "[FINAL]"
            color = C_GREEN if is_formatted else C_CYAN
            print(f"{color}{tag}{C_RESET} {text}")

            # AAI v3 Turn messages do not carry a turn-finalize latency field,
            # so we time it locally: first-partial -> end_of_turn wall clock.
            if turn_start_ts is not None:
                cfg.timings["stt_final_ms"] = (time.perf_counter() - turn_start_ts) * 1000
                turn_start_ts = None

            if translate_q is not None:
                await translate_q.put(text)


async def run_aai_session(
    cfg: DemoConfig,
    audio_q: asyncio.Queue[bytes],
    translate_q: asyncio.Queue[str] | None,
    stop_evt: asyncio.Event,
) -> None:
    """Open the WS, send the per-session config (keyterms), run sender + receiver.

    Reconnects exactly once on a clean transport drop. Anything beyond that is
    a real failure and we let it propagate so the operator sees it.
    """
    url = build_aai_url(cfg)
    # Authorization header is the raw key. NO "Bearer " prefix (AAI v3 quirk).
    headers = {"Authorization": cfg.aai_key}

    attempts = 0
    while attempts < 2 and not stop_evt.is_set():
        attempts += 1
        try:
            print("Connecting to AssemblyAI Universal-3 Pro Streaming...")
            # NOTE: `additional_headers` is the websockets >=14 keyword. The earlier
            # name `extra_headers` was removed in 14.0. requirements.txt pins
            # websockets>=14 to match.
            async with websockets.connect(url, additional_headers=headers, max_size=2**20) as ws:
                # Per-session config goes as a JSON text frame after connect.
                if cfg.keyterms:
                    await ws.send(json.dumps({"type": "UpdateConfiguration", "keyterms_prompt": cfg.keyterms}))
                    print(f"{C_DIM}[session] keyterms loaded: {len(cfg.keyterms)} term(s){C_RESET}")

                print("Speak now. Press Ctrl+C to stop.\n")

                sender = asyncio.create_task(aai_sender(ws, audio_q, stop_evt))
                receiver = asyncio.create_task(aai_receiver(ws, cfg, translate_q, stop_evt))

                done, pending = await asyncio.wait(
                    {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()

                # Polite close. Lets AAI flush any in-flight finals.
                try:
                    await ws.send(json.dumps({"type": "Terminate"}))
                except ConnectionClosed:
                    pass

                if stop_evt.is_set():
                    return

        except (ConnectionClosed, OSError) as exc:
            if attempts >= 2 or stop_evt.is_set():
                raise
            backoff = 1.5
            print(f"{C_YELLOW}[ws] disconnected ({exc}); retrying in {backoff}s...{C_RESET}", file=sys.stderr)
            await asyncio.sleep(backoff)


# ---------------------------------------------------------------------------
# Optional translation + TTS pipeline
# ---------------------------------------------------------------------------

async def translate_loop(
    cfg: DemoConfig,
    translate_q: asyncio.Queue[str],
    tts_q: asyncio.Queue[str] | None,
    stop_evt: asyncio.Event,
) -> None:
    """GPT-4o-mini translation with a rolling 2-turn context window."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=cfg.openai_key)
    history: list[dict[str, str]] = []
    system = (
        f"You are a translator for an iTranslate handheld device. "
        f"Translate the user's text from {cfg.source_lang} to {cfg.target_lang}. "
        "Return ONLY the translated text, no commentary, no quotes."
    )

    while not stop_evt.is_set():
        try:
            text = await asyncio.wait_for(translate_q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        t0 = time.perf_counter()
        messages = [{"role": "system", "content": system}, *history[-4:], {"role": "user", "content": text}]
        try:
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.2,
                max_tokens=200,
            )
            translated = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # surface the failure but keep the demo alive
            print(f"{C_YELLOW}[translate] {exc}{C_RESET}", file=sys.stderr)
            continue

        cfg.timings["translate_ms"] = (time.perf_counter() - t0) * 1000
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": translated})

        print(f"{C_CYAN}[TRANSLATE-{cfg.target_lang.upper()}]{C_RESET} {translated}")

        if tts_q is not None:
            await tts_q.put(translated)


async def tts_loop(
    cfg: DemoConfig,
    tts_q: asyncio.Queue[str],
    playback_q: asyncio.Queue[bytes],
    stop_evt: asyncio.Event,
) -> None:
    """ElevenLabs Flash v2.5 streaming TTS, pushing PCM chunks to playback_q."""
    from elevenlabs.client import AsyncElevenLabs

    client = AsyncElevenLabs(api_key=cfg.elevenlabs_key)
    # A neutral, multilingual voice. Real device would use a per-language pick.
    voice_id = "EXAVITQu4vr4xnSDxMaL"

    while not stop_evt.is_set():
        try:
            text = await asyncio.wait_for(tts_q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        print(f"{C_DIM}[SPEAK] speaking...{C_RESET}")
        t0 = time.perf_counter()
        first_byte_logged = False
        try:
            stream = client.text_to_speech.convert_as_stream(
                voice_id=voice_id,
                text=text,
                model_id="eleven_flash_v2_5",
                output_format="pcm_16000",
            )
            async for chunk in stream:
                if not first_byte_logged:
                    cfg.timings["tts_first_byte_ms"] = (time.perf_counter() - t0) * 1000
                    first_byte_logged = True
                await playback_q.put(chunk)
        except Exception as exc:
            print(f"{C_YELLOW}[tts] {exc}{C_RESET}", file=sys.stderr)
            continue

        # Per-turn latency dump after TTS finishes streaming.
        t = cfg.timings
        print(
            f"{C_DIM}STT-final: {t.get('stt_final_ms', 0):.0f}ms, "
            f"translate: {t.get('translate_ms', 0):.0f}ms, "
            f"TTS-first-byte: {t.get('tts_first_byte_ms', 0):.0f}ms{C_RESET}"
        )


async def playback_loop(playback_q: asyncio.Queue[bytes], stop_evt: asyncio.Event) -> None:
    """Drain TTS PCM chunks into the default output device."""
    out = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    out.start()
    try:
        while not stop_evt.is_set():
            try:
                chunk = await asyncio.wait_for(playback_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            arr = np.frombuffer(chunk, dtype=np.int16)
            out.write(arr)
    finally:
        out.stop()
        out.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def amain(cfg: DemoConfig) -> None:
    """Wire up coroutines and run until Ctrl+C."""
    stop_evt = asyncio.Event()
    audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
    translate_q: asyncio.Queue[str] | None = asyncio.Queue() if cfg.enable_translation else None
    tts_q: asyncio.Queue[str] | None = asyncio.Queue() if cfg.enable_tts else None
    playback_q: asyncio.Queue[bytes] = asyncio.Queue()

    # SIGINT + SIGTERM both flip the stop event so every coroutine unwinds.
    def _shutdown() -> None:
        if not stop_evt.is_set():
            print(f"\n{C_DIM}[shutdown] stopping...{C_RESET}")
            stop_evt.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _shutdown)

    tasks: list[asyncio.Task[Any]] = [
        asyncio.create_task(mic_capture(audio_q, stop_evt)),
        asyncio.create_task(run_aai_session(cfg, audio_q, translate_q, stop_evt)),
    ]
    if cfg.enable_translation and translate_q is not None:
        tasks.append(asyncio.create_task(translate_loop(cfg, translate_q, tts_q, stop_evt)))
    if cfg.enable_tts and tts_q is not None:
        tasks.append(asyncio.create_task(tts_loop(cfg, tts_q, playback_q, stop_evt)))
        tasks.append(asyncio.create_task(playback_loop(playback_q, stop_evt)))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        _shutdown()
    finally:
        stop_evt.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Give Windows ProactorEventLoop a moment to finish tearing down SSL
        # transports before the loop closes. Without this, Python's GC fires a
        # benign but noisy "Event loop is closed" traceback during shutdown.
        # macOS and Linux users do not see this; the sleep is harmless there.
        await asyncio.sleep(0.25)


def main() -> None:
    """Entry point. Catches Ctrl+C cleanly on Windows where add_signal_handler is unavailable."""
    args = parse_args()
    cfg = load_config(args)
    try:
        asyncio.run(amain(cfg))
    except KeyboardInterrupt:
        print(f"\n{C_DIM}[shutdown] bye{C_RESET}")


if __name__ == "__main__":
    main()
