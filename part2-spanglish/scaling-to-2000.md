# Scaling to 2,000 Concurrent Streams

**Customer:** Spanglish Inc.  
**Endpoint:** `wss://streaming.assemblyai.com/v3/ws` (Universal Streaming v3)  
**Use case:** Court-interpreter note-takers, mixed EN/ES speech, 2000 concurrent WebSockets

---

## 0. Incident Acknowledgement

The `encoding=opus` mismatch and missing `speech_model` parameter that caused 1007/1008 closes are now fixed in your Java client. With those corrections in place, your connections will establish cleanly and remain stable. This document outlines the rollout strategy to reach 2000 concurrent streams safely.

---

## 1. How AssemblyAI Handles Concurrent Load

AssemblyAI does NOT enforce a hard cap on total concurrent streams. Instead, the service manages *new connection attempts per minute* using an adaptive rate limit. This limit starts at a baseline tied to your plan tier and automatically increases 10% every 60 seconds when utilization exceeds 70%.

When new-session attempts exceed the current limit, the server returns HTTP 429 or WebSocket close code 1008, signaling backoff. This is a feature, not a bug: it prevents sudden traffic spikes from cascading across your infrastructure.

**How this affects your rollout:** You don't need a concurrency-increase ticket. Instead, coordinate with your Customer Success Manager (CSM) before your launch window so the per-minute limit is pre-warmed for your expected traffic shape. Share your peak traffic profile (sessions/min, duration, geographic distribution, retry patterns) and we can tune the baseline and growth curve in advance.

---

## 2. Connection Architecture

Each WebSocket connection is independent. Design your client as follows:

- **Virtual threads or thread pool:** Issue N parallel connection attempts from a bounded pool (e.g., 200 threads for a 2000-stream load, ~10 streams/thread).
- **Connect timeout:** Budget 3 seconds from SYN to Subprotocol Negotiation complete.
- **Exponential backoff with jitter:** On 1008, wait 2^attempt seconds + random(0, 1s). Cap at 30 seconds.
- **Session resumption:** Keep `session_id` in memory after Terminate. If a reconnect happens within the session expiry window (default 900s), the service picks up partial transcripts and audio context.
- **Idle timeout:** The server closes inactive streams after 60 seconds. Send at least one audio frame per 60 seconds or ping-pong keep-alives. Spanglish note-takers often have silent pauses; structure your app to handle 60s inactivity gracefully.
- **Region pinning:** All Spanglish connections should pin to a single region (default US East 1). Do not round-robin across regions mid-session.

---

## 3. Audio Pipeline

Stream raw PCM s16le at 16 kHz, mono or dual-channel depending on speaker layout (interpreter + party).

**Packet pacing and buffering:**
- Capture audio in 50ms chunks (16 kHz * 50ms = 800 samples = 1,600 bytes @ 16-bit).
- Accumulate 200ms (3-4 frames) before sending the first message. This pre-buffer reduces jitter from capture timing.
- Space subsequent frames every 50ms on the wall clock, even if capture jittered. Use a pacing thread or timer queue.

**Bandwidth math:**
- 1 stream = 16 kHz * 2 bytes/sample = 32 KB/s raw audio.
- At 2000 concurrent streams, inbound audio bandwidth = 2000 * 32 KB/s = 64 MB/s.
- Outbound transcript + metadata bandwidth (mixed EN/ES, streaming tokens) ~= 8 KB/s per stream (varies with speech rate).
- Total egress: 2000 * 8 KB/s = 16 MB/s.
- Peak egress including retransmits and observability telemetry: ~512 Mbps, or roughly 0.5 Gbps. Confirm your egress capacity with your network operations team.

---

## 4. Failure Modes and Response

| Close Code | Meaning | Your Action |
|---|---|---|
| 1000 | Normal close | Transcript finalized, session complete. No action. |
| 1006 | Abnormal close (network) | Reconnect with backoff. Resume if within session expiry. |
| 1008 | Policy violation (rate limit hit) | Wait 2 seconds, then retry with exponential backoff. Do not retry immediately. |
| 1011 | Server error | Reconnect. If persistent, notify AssemblyAI support with session ID and timestamp. |
| Silent stall (no frames for 90s) | Connection stuck, no activity, no close | Proactive timeout: close client-side and reconnect. Use a 90s read deadline on the socket. |

**Maintenance windows:** AssemblyAI observes planned maintenance ~1x per quarter during US off-peak hours (typically 0200-0400 UTC). Connections may close with 1006. Implement graceful shutdown + reconnect logic. Monitor for service status updates at https://status.assemblyai.com.

---

## 5. Observability

Instrument every connection with these signals:

- **session_id:** Captured from the Begin event; log it immediately.
- **connect_latency_ms:** Time from WebSocket open to Subprotocol Negotiation complete.
- **first_token_latency_ms:** Time from first audio frame sent to first Turn event with non-empty transcript.
- **turn_finalize_latency_ms:** Time from Turn event with turn_is_formatted=true to the next event (streaming latency).
- **disconnect_code and reason:** Log the close code (1000, 1006, 1008, etc.).
- **audio_dropped_frames:** Count frames that arrived out of sequence or never arrived.
- **partial_to_final_ratio:** Percentage of transcript tokens that were overwritten in a later Turn event (indicates ASR confidence swings).
- **reconnect_count and duration:** How many times the session reconnected, and how long each reconnect took.

Export these to your APM/logging backend (e.g., Datadog, New Relic, ELK). Set alerts on:
- first_token_latency_ms > 800ms (trigger investigation)
- audio_dropped_frames > 1% (packet loss issue)
- disconnect_code == 1008 rate > 0.1 per second (rate limit being hit)

---

## 6. Capacity Rollout Schedule

Ramp up in stages. Each stage has an exit criterion; do not proceed until it is met.

| Stage | Concurrent Streams | Duration | Exit Criteria |
|---|---|---|---|
| **1. Proof of Concept** | 50 | 48 hours | p95 first-token latency under 600ms, zero 1008 closes, 100% audio delivery |
| **2. Load Test** | 200 | 72 hours | Reconnect rate under 0.5%, audio drop rate under 0.1%, egress stable at ~64 Mbps, no NAT exhaustion on client side |
| **3. Ramp** | 800 | 1 week | Egress holds at 256 Mbps, turn-finalize latency p95 < 300ms, speech-model library stays warm (no ASR model evictions) |
| **4. Full Scale** | 2000 | Ongoing | All SLOs green for 7 consecutive days, support team reports zero escalations tied to audio or transcript quality |

Between stages, debrief with your CSM and our team. Share metrics, clarify blockers, and confirm readiness to proceed.

---

## 7. Cost Framing

Streaming v3 charges at **$0.15 per concurrent stream-hour** (billed monthly).

**Spanglish's projected load:**
- 2000 concurrent streams
- Average 8 hours per court day
- 22 billable days per month (business days, holidays excluded)

Calculation: 2000 * 8 * 22 * $0.15 = **$52,800 per month**

Budgeted range: **$50,000 to $55,000 per month**. AssemblyAI can discuss enterprise volume discounts for multi-year commitments.

---

## 8. Next Steps

1. **Coordinate with your CSM** to pre-warm the per-minute rate limit for your traffic profile.
2. **Deploy Stage 1** (50 concurrent) to a staging environment matching your production topology.
3. **Collect observability data** for 48 hours and validate all metrics in section 5.
4. **Schedule a debrief** with your engineering team and ours to review metrics and approve Stage 2.
5. **Proceed through stages 2, 3, 4** in sequence, holding each for its required duration and exit criteria.

Questions? Reach out to your CSM or reply to this email.
