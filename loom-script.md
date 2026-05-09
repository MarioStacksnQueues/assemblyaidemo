# Loom recording script

A timestamped script for the bonus Loom video. Target 4:30, hard ceiling 5:00. One take. Read in a calm, warm-but-decisive voice (think senior FDE briefing a peer, not pitch-deck energy).

## Line-number cheat sheet (keep this open in a second window while recording)

**SpanglishFixed.java**
- Lines 78-90: API_ENDPOINT block with all three URL fixes (encoding=pcm_s16le, speech_model=u3-rt-pro, language_detection, speaker_labels, max_speakers).
- Line 84: `&encoding=pcm_s16le` (BLOCKER #1 fix).
- Line 83: `&speech_model=u3-rt-pro` (BLOCKER #2 fix).
- Lines 111-116: `main()` method with `new SpanglishFixed()` constructor (BLOCKER #3 fix).
- Line 58: `FRAMES_PER_BUFFER = 800` (50 ms chunks, was 25 ms).
- Line 189: `reconnectWithBackoff()` (capped exponential backoff).
- Line 173: `RandomAccessFile` streaming WAV write (no heap growth).
- Line 258: `cleanupCalled.compareAndSet` (idempotency guard).
- Line 375: `describeCloseCode()` (human-readable AAI close codes).

**demo.py**
- Lines 22-43: STT accuracy levers comment block (six levers explained).
- Lines 155-168: `build_aai_url()` (same u3-rt-pro config as Spanglish).
- Lines 115-116: `--enable-translation` and `--enable-tts` flag definitions.
- Line 326: keyterms sent as `UpdateConfiguration` JSON frame after connect.

Open both files in VS Code BEFORE you hit record so you can `Ctrl+G` to any line in <1 second.



## Pre-recording setup

- **Webcam:** ON. Small bubble, bottom-right.
- **Mic:** External USB if available (Yeti, MV7). Laptop mic only if not. Test playback first.
- **Screen:** 1440p or 1080p. VS Code font 16-18 pt. Terminal font 16 pt.
- **Loom mouse highlighter:** ON.
- **Notifications:** all off (Slack quit, phone face-down, email quit).
- **Two practice runs end-to-end** before recording the real one. Do not over-rehearse.

## The demo runs LIVE during the Loom

Run `python demo.py` live during the recording. Reviewers see real partials roll in, then the green `[TURN]` line. Highest-trust artifact in the video and demonstrates exactly the skill the role requires (live demos for customers).

Mitigations:
- Practice the demo segment twice before the real take. Two short sentences, `Ctrl+C`, done.
- Keep `sample-output.txt` open as a tab as a fallback. If the live run hiccups, say "I've got a captured run in the repo" and click that tab. Almost certainly not needed, but pre-positioned just in case.
- Have a terminal window pre-`cd`'d into `part1-itranslate/` so all you do at the demo segment is type `python demo.py`.

## The script

Stage directions in `[brackets]`. Pauses marked `(pause)`. Read at ~150 WPM.

---

### 0:00 to 0:20 — Open + triage statement

`[Webcam full screen. Mario on camera. No smile yet, eye contact.]`

> Hi, I'm Mario Cuevas. Spanglish was production-down so I took that first. Fix, customer email, scaling guide, privacy answer. Then iTranslate. Let me show you.

`[Click to file tree view of the repo.]`

---

### 0:20 to 1:35 — Spanglish bug walkthrough

`[VS Code: open SpanglishFixed.java. Press Ctrl+G, type 78, Enter. Cursor lands on the API_ENDPOINT block.]`

**Look at lines 78 to 90.** The full URL builder with all three URL fixes is right here.

> Three blockers stacked. (pause) First, the URL declared `encoding=opus` but the code captured raw 16-bit PCM. v3 only supports `pcm_s16le` and `pcm_mulaw`. The server could not decode any audio.

`[Highlight line 84: "+ "&encoding=pcm_s16le"`. Read it.]`

> Second, the URL was missing the required `speech_model` parameter. v3 has no default model. Without it the handshake fails. For their bilingual EN/ES court use case, `u3-rt-pro` is the right value: native code-switching, `language_detection`, `speaker_labels`.

`[Highlight line 83: "+ "&speech_model=u3-rt-pro"`. Then briefly slide cursor down to lines 86 to 88 to show language_detection, speaker_labels, max_speakers.]`

`[Press Ctrl+G, type 111, Enter. Lands on the main() method.]`

**Look at lines 111 to 116.** The class-vs-constructor fix.

> Third, `main()` instantiated `new StreamingTranscription()`, but the class is `Spanglish`. The file would not compile. (pause) Their integration logic was solid. Their Begin, Turn, and Termination message handling was correct out of the box. The breakage was config and a constructor typo.

`[Highlight line 115: "SpanglishFixed transcription = new SpanglishFixed();"]`

`[Now use Ctrl+F to search "// FIX:" and let it cycle through the matches.]`

**The reliability fixes**: line 58 (`FRAMES_PER_BUFFER = 800`), line 189 (`reconnectWithBackoff`), line 173 (`RandomAccessFile` streaming WAV write), line 258 (`cleanupCalled.compareAndSet` idempotency), line 375 (`describeCloseCode` mapping).

> While I was in there, I added reconnect with exponential backoff, streamed the WAV recording incrementally to disk so the heap stays flat at scale, made `cleanup()` idempotent, and mapped the AAI close codes to human-readable strings. Seven hardening fixes total, all marked with `// FIX:` comments.

---

### 1:35 to 2:05 — Comms walkthrough

`[Open customer-email.md.]`

> Customer email leads with the good news that v3 is fine and their integration logic was correct. No blame. Three fixes explained in plain language. Pointers to the scaling and privacy docs. Offers a 30-minute call with their eng team.

`[Quick scroll across scaling-to-2000.md, privacy-and-retention.md, internal-engineering-summary.md, ooo-handoff.md.]`

> Scaling doc walks them from 50 to 2000 in four stages with the per-minute rate-limit framing. Privacy doc is conditional on opt-out, with the DPA and BAA paths called out. Internal RCA tells engineering it's not a service bug. OOO handoff so the original engineer can pick up Monday with full context.

---

### 2:05 to 2:20 — Bridge

`[Click in the file tree from part2-spanglish/ to part1-itranslate/. Let the click land. 2 seconds of silence.]`

> Same engineer, same repo, different customer posture. iTranslate is a prospect.

---

### 2:20 to 3:30 — iTranslate demo

`[Switch to a terminal window already cd'd into part1-itranslate/. Type "python demo.py" and hit Enter.]`

> iTranslate makes a battery-powered translation device with no GPU, so all inference happens in the cloud. The demo simulates the device by streaming my laptop mic to AAI's Universal-3 Pro Streaming endpoint.

`[Wait for "Speak now. Press Ctrl+C to stop." Then say a short test sentence into the mic.]`

> This is Mario testing the Universal-3 Pro Streaming demo for the take-home submission. Court interpreters need accurate transcription in real time.

`[Wait for the [TURN] line to land. Pause 1 second so the viewer reads it. Then Ctrl+C.]`

> Sub-second from speech-end to formatted final, with capitalization and punctuation. That is `format_turns=true` plus `u3-rt-pro` doing the work.

`[While terminal plays, switch focus to demo.py. Press Ctrl+G, type 155, Enter.]`

**Look at lines 155 to 168 (`build_aai_url`).** Same `u3-rt-pro` config we just gave Spanglish: `speech_model=u3-rt-pro`, `format_turns=true`, `language_detection=true`, `encoding=pcm_s16le`.

> The URL is the same `u3-rt-pro` config we just gave Spanglish. Optional `--enable-translation` and `--enable-tts` flags add GPT-4o-mini and ElevenLabs Flash for full pipeline.

`[Press Ctrl+G, type 115, Enter. Lands on the flag definitions in parse_args.]`

**Lines 115 to 116** show the flag definitions. **Line 326** is where keyterms are sent to AAI as `UpdateConfiguration`.

> STT-only is the safe default for a one-take video. Translation and TTS work in the same script, just gated behind flags.

---

### 3:30 to 4:05 — Architecture and scaling

`[Open part1-itranslate/architecture.md. Use VS Code's "Open Preview" (Ctrl+Shift+V) to render the Mermaid diagrams.]`

> Architecture doc has the latency budget. STT first partial 150 ms, formatted final 300 ms after speech ends, translation 400 to 600, TTS first byte 150. Total under 1.2 seconds.

`[Scroll to the latency budget table. Then back to the demo.py header to show the 6 levers comment block.]`

**demo.py lines 22 to 43** is the STT accuracy levers comment block, all six listed with brief reasoning.

> Six accuracy levers iTranslate can tune per device, per environment. Headline: `keyterms_prompt` for proper nouns is the single biggest gain. (pause)

`[Open typescript-proxy-example.ts. Scroll to the connection setup section.]`

> TypeScript proxy skeleton for their integration team. Keeps the API key off battery devices.

`[Click into evaluation-plan.md, show the table of metrics or the test corpus section.]`

> Plus an evaluation plan with WER methodology and a 150-sample test corpus so they can prove the gain with numbers, not vibes.

---

### 4:05 to 4:30 — Close

`[Webcam full screen. Mario on camera.]`

> Both pieces are in the repo. Happy to walk through anything in the interview.

`[1 second of silence. Slight nod. Stop recording.]`

---

## Anti-patterns to avoid

- No "thanks for watching."
- No "let me know if you have any questions."
- No nervous laugh at the end.
- No upward inflection on declarative statements.
- No apologizing for length or technical density.
- No "I think" or "probably" when describing the fixes; you fixed them, you know.
- No filler words (um, like, kinda) when explaining the bugs; let silence carry the weight.

## Backup plan

If the demo footage fails to play during the Loom, narrate over the demo.py code instead and say: "I have a recorded run in `sample-output.txt` in the repo." Reviewers will check.

## After recording

- Trim 1-2 seconds off the start and end if needed.
- Title the Loom: "AssemblyAI Applied AI Engineering take-home (Mario Cuevas)"
- Set sharing: anyone with the link.
- Paste the Loom URL into the top-level `README.md` in the placeholder.
- Paste the Loom URL into the Greenhouse submission field.
