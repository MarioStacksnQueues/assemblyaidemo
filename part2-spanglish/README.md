# Part 2: Spanglish Inc. critical issue

A production customer (Spanglish Inc., note-takers for English and Spanish court proceedings with interpreters) reported "your product doesn't work at all" on AssemblyAI's Universal Streaming v3. Original Applied AI Engineer was OOO; I jumped in.

This folder contains the fixed code, the customer email, the scaling guidance, the privacy answer, the internal RCA, and the OOO handoff.

## What's in this folder

| File | Audience | Purpose |
|------|----------|---------|
| `SpanglishFixed.java` | Customer engineering | Corrected client. Every change inline-commented with `// FIX:`. |
| `customer-email.md` | Customer business + eng | Empathetic reply that delivers the fix and signposts scaling and privacy. |
| `scaling-to-2000.md` | Customer engineering | Staged rollout, bandwidth math, per-minute rate-limit framing, observability. |
| `privacy-and-retention.md` | Customer legal + eng | Conditional opt-out language, compliance posture, customer-side responsibilities. |
| `internal-engineering-summary.md` | AAI engineering team | RCA confirming v3 service is fine. Three blockers were entirely in the client. |
| `ooo-handoff.md` | AAI colleague | Clean handoff so the original engineer picks up Monday without re-doing diligence. |

## The three blockers

Any one of these alone causes "doesn't work at all." All three were in the customer's hand-rolled Java client. None were AssemblyAI service issues.

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | BLOCKER | URL declared `encoding=opus` but code captured raw 16-bit signed little-endian PCM. v3 only supports `pcm_s16le` (default) or `pcm_mulaw`. Server could not decode the audio. | `encoding=pcm_s16le` |
| 2 | BLOCKER | URL was missing the required `speech_model` parameter. v3 has no default; every connection must specify a model. | Added `speech_model=u3-rt-pro` |
| 3 | BLOCKER | `main()` instantiated `new StreamingTranscription()` but the class is `public class Spanglish`. The file would not compile. | Match constructor to class. |

Plus seven reliability fixes that would have surfaced under load. Full table in `internal-engineering-summary.md`.

## What the customer's code got right

Their v3 message protocol handling was correct. They properly handled `Begin`, `Turn`, and `Termination` events with the right field names (`id`, `expires_at`, `transcript`, `turn_is_formatted`, `audio_duration_seconds`, `session_duration_seconds`) and used the `{"type":"Terminate"}` teardown correctly. The integration thinking was sound. The breakage was entirely in the WebSocket query string and one class-name typo.

This matters for the internal engineering summary: the v3 service is functioning as designed. We are not on the hook for a code change.

## How I worked the escalation

1. Read the failing code and reproduced the failure mode against AAI Streaming v3 docs.
2. Confirmed the three blockers and seven reliability issues by reading the source line by line.
3. Wrote `SpanglishFixed.java` with every change marked.
4. Drafted the customer email leading with empathy and the good news that the v3 service is fine.
5. Wrote the scaling guidance and the privacy answer as standalone docs the customer's eng and legal teams can read independently.
6. Wrote the internal RCA so AAI engineering can close the ticket without taking on a service-side fix.
7. Wrote the OOO handoff so the original engineer can pick up Monday with full context.

## Compile the fixed code

```bash
# Requires gson and Java-WebSocket on the classpath.
javac -cp "gson.jar:Java-WebSocket.jar" SpanglishFixed.java
java  -cp ".:gson.jar:Java-WebSocket.jar" com.assemblyai.SpanglishFixed
```

JARs are not bundled (deliberately, so reviewers do not pull binaries from a take-home). Either is one Maven Central download.

## Reading order

For a 5-minute review:

1. `internal-engineering-summary.md` (RCA, 3 minutes).
2. `SpanglishFixed.java` `// FIX:` comments only (skim, 1 minute).
3. `customer-email.md` (1 minute).

For a deeper read, follow with `scaling-to-2000.md` and `privacy-and-retention.md` in either order.
