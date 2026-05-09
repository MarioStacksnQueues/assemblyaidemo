# Handoff: Spanglish Inc. Account

**HANDOFF FROM:** Mario Cuevas, Applied AI Engineering  
**HANDOFF TO:** <colleague_name>  
**DATE:** 2026-05-08  
**ACCOUNT:** Spanglish Inc.  
**USE CASE:** Court-interpreter note-takers using AssemblyAI Streaming v3 for mixed EN/ES speech transcription

---

## Resolution Status

**CLOSED.** Three blocker bugs in the customer's Java WebSocket client have been identified, fixed, and delivered. No AssemblyAI service issue. Customer is moving to capacity ramp plan (Stage 1: 50 concurrent, 48h validation).

---

## What They Received from Mario

- **SpanglishFixed.java** - Corrected client code with all blockers (encoding, speech_model, class naming) and secondary issues resolved. Includes inline comments.
- **scaling-to-2000.md** - Architecture guide for staged rollout: 50 -> 200 -> 800 -> 2000 concurrent streams, with exit criteria per stage.
- **privacy-and-retention.md** - Data handling, compliance posture, opt-out flow for model training, BAA/DPA guidance for court proceedings.
- **internal-engineering-summary.md** - RCA for our team showing customer protocol implementation is correct; all failures were client-side connection params.
- **customer-facing email** - High-level summary of blockers, fixes, scaling plan, next steps (separate document).

---

## Open Items / Next Moves

1. **Stage 1 validation (48h)** - Customer will deploy SpanglishFixed.java to staging, run 50 concurrent streams. Owner: Spanglish eng team. Success criteria: p95 first-token latency < 600ms, zero 1008 closes, 100% audio delivery.
2. **Debrief and Stage 2 approval** - After 48h, customer shares metrics with CSM. Review together, confirm readiness. Owner: <csm_name> + Spanglish eng lead.
3. **Model training opt-out email** - Customer emails data-opt-out@assemblyai.com to opt out (required for zero-retention guarantee). Owner: Spanglish legal/compliance. ETA: concurrent with Stage 1.
4. **DPA and BAA execution** - Customer legal team reviews, signs DPA (standard) and BAA (if PHI in scope). Owner: <legal_owner> + Spanglish legal. ETA: before production launch.
5. **Ongoing observability** - Customer continues logging the metrics defined in scaling-to-2000.md section 5 and shares monthly reports with CSM. Owner: Spanglish ops + CSM.

---

## Customer Mood at Last Touch

Relieved and confident. They appreciated getting a fixed code sample and a clear rollout roadmap rather than vague debugging suggestions. The three blockers were frustrating but straightforward once identified. They are committed to the staged ramp.

---

## Risks to Watch

1. **Rate limit hits during Stage 2-3 ramp.** If per-minute rate limit was not pre-warmed by CSM, customer will hit 1008 closes and assume a service issue. Mitigation: CSM to confirm pre-warm was done before customer starts Stage 2. If not done, do it now.
2. **Audio jitter on court proceedings.** Spanglish note-takers run in real-time court environments with spotty WiFi and variable latency. Our 60s idle timeout and the customer's reconnect logic will handle it, but first-token latency swings could frustrate judges/interpreters. Mitigation: rehearse on low-quality network in staging. Log every 1008/1006 with session ID for quick root-cause analysis if it happens in production.
3. **BAA execution delays.** If Spanglish processes PHI (medical testimony, healthcare interpreting), legal will push for BAA. If their legal team is slow, they may launch before BAA is signed, then discover HIPAA compliance gap post-production. Mitigation: <legal_owner> to flag BAA as blocking any healthcare-related usage; remind customer via CSM during Stage 1 debrief.

---

## Contract Implications

- **Plan tier required:** Enterprise or Professional (Streaming v3 is not available on Free/Hobby tiers).
- **Model training opt-out:** Available on paid plans; requires email to data-opt-out@assemblyai.com. No extra charge.
- **BAA:** If they process PHI, BAA is required before use. Standard add-on, no extra charge. <legal_owner> will prepare template; Spanglish legal signs.
- **Cost:** ~$50-55K/month @ 2000 concurrent streams * 8h/day * 22 court days/month. Discussed with CSM; enterprise discount available on multi-year commitment.
- **Support tier:** Escalation support recommended (included in Enterprise); CSM check-ins weekly during ramp phases 1-3, monthly thereafter.

---

## Key Contacts

- **Spanglish engineering lead:** [Contact TBD by Mario during handoff call]
- **Customer Success Manager:** <csm_name>
- **AssemblyAI legal owner for BAA/DPA:** <legal_owner>

---

## Transition Notes

This is a straightforward handoff. The hard part (debugging the Java client) is done. Your role is to:
1. Ensure CSM pre-warmed the rate limit (confirm via CSM before Stage 2).
2. Monitor metrics and stage approvals as they come in (weekly during Stages 2-4).
3. Escalate any 1008 patterns or audio-quality regressions immediately to on-call engineering.
4. Follow up with BAA execution status with <legal_owner> by end of week (if they are processing PHI).
5. Check in with customer mid-Stage 3 to confirm egress stabilization and NAT behavior.

Otherwise, this account is on a well-defined path to 2000 concurrent. Let them execute, monitor the metrics, and celebrate when they hit Stage 4.
