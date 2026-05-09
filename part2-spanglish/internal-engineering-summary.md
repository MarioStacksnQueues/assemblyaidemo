# RCA: Spanglish Inc. Streaming v3 Integration

**TO:** Engineering / On-call rotation  
**RE:** Spanglish Inc. RCA / Streaming v3 (CLOSED)  
**DATE:** 2026-05-08  
**SEVERITY:** Customer-side blocker (no service issue)

---

## TL;DR

Spanglish's "product doesn't work" report was caused by three blocker bugs in their Java WebSocket client, not an AssemblyAI service issue. All three are customer-side and all are fixed. The customer's v3 protocol handling was correct; the integration failures were pre-connection and class-definition issues.

---

## Evidence: Customer's v3 Protocol Handling Is Sound

We confirmed that Spanglish's client correctly implements the v3 message protocol:

- **Begin event:** Captures `id` and `expires_at` correctly. Uses session ID for logging and reconnect eligibility.
- **Turn event:** Parses `transcript`, `turn_is_formatted`, and `confidence` fields correctly. Applies turn-finalize logic when `turn_is_formatted=true`.
- **Termination event:** Extracts `audio_duration_seconds` and `session_duration_seconds`, passes to cleanup handlers correctly.
- **Teardown message:** Recognizes the `{"type":"Terminate"}` frame and closes the WebSocket cleanly.

This protocol implementation tells us the customer's fundamental understanding of v3 is solid. Their integration logic was not broken. The failures were upstream: connection parameters and Java class structure.

---

## Root Cause Analysis

| Issue | Severity | Category | Customer-side Fix |
|---|---|---|---|
| **URL encoding mismatch** | BLOCKER | Connection param | Change `encoding=opus` to `encoding=pcm_s16le` in WebSocket URL. Raw 16-bit signed little-endian PCM is what the client sends; the URL must declare this. Server could not decode opus-encoded parameter header. |
| **Missing speech_model parameter** | BLOCKER | Connection param | Add `speech_model=u3-rt-pro` to the WebSocket URL query string. Streaming v3 requires explicit model selection; there is no default. Without it, the server rejects the handshake. Universal-3 Pro is the right model for their EN/ES use case (native code-switching, language_detection, speaker_labels). |
| **main() instantiation error** | BLOCKER | Class definition | The file declares `public class Spanglish` but `main()` invokes `new StreamingTranscription()`. Either rename the class or change the constructor call. The fix in `SpanglishFixed.java` matches the constructor call to the existing class name. Without one of those, the file does not compile. |
| **25ms buffer below minimum** | HIGH | Audio pipeline | Increase `FRAMES_PER_BUFFER` from 400 to 800 (25 ms to 50 ms at 16 kHz). Streaming v3 expects chunks of 50 to 1000 ms. Undersized frames inflate per-message overhead and can confuse server-side voice-activity detection. |
| **No reconnect logic** | HIGH | Resilience | Wrap the WebSocket connect in a capped exponential-backoff retry loop (initial 500 ms, cap 30 s, full jitter, 5 attempts). The original `onClose` and `onError` both unconditionally set `stopRequested`, so any transient network blip ends a multi-hour court session. |
| **Unbounded recordedFrames heap** | HIGH | Memory | Stream PCM bytes incrementally to disk via `RandomAccessFile`. The original code accumulated every audio frame in an unbounded `ArrayList`. A 30-min session is ~57 MB per stream; at 2,000 concurrent streams that is ~114 GB of heap. The fix reserves a 44-byte WAV header at file open, appends raw PCM as it arrives, and patches the header sizes at session end. Memory stays flat. |
| **audioThread.join too short, no interrupt** | MEDIUM | Shutdown | Increase the join timeout from 1000 ms to 3000 ms, call `microphone.stop()` BEFORE the join (the only call that unblocks `microphone.read()`), and `audioThread.interrupt()` to cover the race. Original code could leave the audio thread buffering while `saveWavFile()` started, racing on `recordedFrames`. |
| **Non-idempotent cleanup** | MEDIUM | Shutdown | Guard `cleanup()` with an `AtomicBoolean cleanupCalled` set via `compareAndSet`. Original shutdown hook plus main-thread catch could both call cleanup, which would write the WAV file twice with the same timestamp filename and corrupt the second write. |
| **Opaque close codes** | LOW | Observability | Map known AAI close codes (4001 auth, 4002 sample rate, 4008 encoding, 1008 rate limit, 1006 abnormal close, 1011 server error) to human-readable strings. Original code printed only the raw integer, making "doesn't work at all" tickets harder to triage. |

---

## What We Delivered to the Customer

1. **SpanglishFixed.java**: corrected client with all three blockers and seven reliability fixes. Every change inline-commented with `// FIX:`.
2. **scaling-to-2000.md**: architecture guide for the staged rollout (50 -> 200 -> 800 -> 2000) with bandwidth math, observability per stream, cost framing, and failure-mode response.
3. **privacy-and-retention.md**: data handling, model-improvement opt-out flow, DPA and BAA paths for the court-proceeding use case, customer-side responsibilities.
4. **customer-email.md**: customer-facing reply leading with the diagnosis, the fix, and signposted attachments for scaling and privacy.
5. **ooo-handoff.md**: clean handoff for the engineer returning from OOO. Open items, risks, and contract implications.

---

## Recommendation

**Consider publishing an official Java quickstart for v3** to reduce integration friction. Spanglish's errors (encoding/model parameter confusion, class naming) are common mistakes that a well-documented working example would prevent. A 200-line reference client showing:
- Correct WebSocket URL construction
- Begin/Turn/Termination event parsing
- Graceful shutdown
- Reconnect with backoff

...would have saved Spanglish hours of debugging and the support team a ticket.

Existing quickstarts exist for Python and JavaScript. Java is conspicuously absent from the Streaming v3 docs. Filling that gap would help enterprise customers who standardize on JVM languages (Spring Boot, Kafka, etc.).

---

## Resolution Status

CLOSED. Customer integration is correct. All fixes are customer-side, deployed, and working. No follow-up engineering action required on AssemblyAI side.
