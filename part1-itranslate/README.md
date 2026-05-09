# Part 1: iTranslate STT demo

A runnable Python demo that simulates iTranslate's handheld translation device by streaming a laptop microphone to AssemblyAI Universal-3 Pro Streaming. Built with Python and asyncio because iTranslate is a Python/TypeScript shop.

## What's in this folder

| File | Purpose |
|------|---------|
| `demo.py` | Single-file runnable demo. Asyncio. Raw WebSocket against `u3-rt-pro`. |
| `requirements.txt` | 6 dependencies, pinned floors. |
| `.env.example` | Three placeholder keys (AAI required, OpenAI and ElevenLabs optional). |
| `architecture.md` | Mermaid pipeline + sequence diagram, latency budget, component decisions. |
| `evaluation-plan.md` | WER methodology, 150-sample test corpus, ablation matrix to prove the gain. |
| `typescript-proxy-example.ts` | Skeleton TS proxy for iTranslate's TypeScript team. |
| `sample-output.txt` | Captured terminal output from a real run. |

## Run it

From this folder:

```bash
cp .env.example .env
# Edit .env and paste your AssemblyAI API key (free tier works).
# OpenAI and ElevenLabs keys only needed for --enable-translation / --enable-tts.

pip install -r requirements.txt

# STT-only, the default. Streams mic to AAI, prints partial and final transcripts.
python demo.py

# Optional: full pipeline with translation and TTS playback.
python demo.py --source-lang en --target-lang es --enable-translation --enable-tts
```

`Ctrl+C` cleanly closes the WebSocket with a `Terminate` message and shuts down the mic.

## CLI flags

| Flag | Default | Notes |
|------|---------|-------|
| `--source-lang` | `en` | Hint passed to AAI; u3-rt-pro auto-detects code-switching. |
| `--target-lang` | `es` | Translation target. Only used with `--enable-translation`. |
| `--keyterms` | none | Path to a text file, one term per line. Sent to AAI as `keyterms_prompt`. |
| `--enable-translation` | off | Calls GPT-4o-mini after each finalized turn. |
| `--enable-tts` | off | Calls ElevenLabs Flash v2.5 on the translated text and plays it. |

## The six STT accuracy levers

These are what iTranslate would tune per device, per environment, per language pair. The demo surfaces all six. See `architecture.md` for the deeper reasoning.

1. **`format_turns=true`** - Returns finalized turns with punctuation and casing. Cleaner input to translation.
2. **`keyterms_prompt`** - Up to ~100 biasing terms. Highest single-lever gain on proper nouns (place names, brand names).
3. **End-of-turn tuning** - `end_of_turn_confidence_threshold`, `min_end_of_turn_silence_when_confident`, `max_turn_silence`. Tuned per use case (fast back-and-forth vs. monologue).
4. **Sample rate and chunk discipline** - 16 kHz mono PCM s16le, 50 ms chunks. The most common avoidable WER hit.
5. **Model selection** - `u3-rt-pro` for code-switching workloads; lighter models when latency dominates.
6. **On-device preprocessing** - AGC, noise suppression, mic geometry. Out of scope for the cloud demo, in scope for iTranslate's hardware team.

## Architecture (one-paragraph version)

`mic_capture` (sounddevice callback) -> `audio_q` -> `aai_sender` -> WSS -> `aai_receiver` -> per-turn fanout to `translate_loop` (GPT-4o-mini) -> `tts_loop` (ElevenLabs Flash) -> `playback_loop` (sounddevice OutputStream). Bounded `asyncio.Queue` between every stage. The mic callback stays trivial (no work, just `loop.call_soon_threadsafe`). Single `stop_evt` for cooperative shutdown so `Ctrl+C` unwinds every task and sends `Terminate` before WS close. Full diagram and per-stage latency targets in `architecture.md`.

## Latency target

End-to-end (last word spoken to translated audio playing) under 1.2 seconds on US WiFi with the full pipeline. STT-only is well under 500 ms from speech end to finalized turn.

## Troubleshooting

- **Windows mic permission denied** - On first run, Windows may silently block mic access. Open Settings, Privacy and Security, Microphone, allow apps to access mic and allow Python specifically. The script logs the chosen audio device on startup; if it picks a non-existent device, set `SD_DEFAULT_DEVICE` env var.
- **No partial transcripts appearing** - Check that the chosen device is actually capturing. The demo prints the device name on startup; speak into THAT mic. On Windows WASAPI, default device sometimes resamples; the demo forces 16 kHz.
- **`extra_headers` error on import** - Make sure `websockets>=14.0` is installed. The 14.0 release renamed the kwarg to `additional_headers`. requirements.txt pins this floor.
- **WebSocket closes immediately with code 4001** - Bad API key. Check the AAI key in `.env`.
- **WebSocket closes with code 4008** - Encoding mismatch. Should not happen with this code (we use `pcm_s16le` to match the mic capture). If it does, the audio device is delivering a format other than int16; check the device specs.

## Cost per run

A 5-minute STT-only run is about 5 cents at AAI list pricing. Adding GPT-4o-mini translation and ElevenLabs Flash TTS brings it to about 25 cents per 5 minutes. Comfortably under a quarter for a thorough demo.

## Out of scope for this demo

Reconnect with exponential backoff, scoped streaming tokens, region pinning, on-device buffering for cellular drops. All discussed in `architecture.md` under "production hardening." The Spanglish Java fix in `part2-spanglish/` shows the reconnect pattern as a reference.
