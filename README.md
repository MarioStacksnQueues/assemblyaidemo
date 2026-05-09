# AssemblyAI Applied AI Engineering Take-Home

**Candidate:** Mario Cuevas
**Role:** Applied AI Engineering, Customer Experience Engineering team
**Submitted:** 2026-05-08

This repo is the full submission. Reviewers should be able to orient in about 60 seconds from this file alone, then drill into either part.

## What's in here

The take-home simulates the real job: build a sales demo for a prospective customer (iTranslate) while simultaneously fixing a production fire for an existing customer (Spanglish Inc.). The two folders below mirror that split.

```
.
├── README.md                       (you are here)
├── loom-script.md                  4-5 minute video script, recording link in section below
├── part1-itranslate/               prospective customer demo
│   ├── README.md                   run instructions, accuracy levers, troubleshooting
│   ├── demo.py                     runnable Python STT demo (asyncio, raw WebSocket against u3-rt-pro)
│   ├── requirements.txt            6 dependencies, pinned floors
│   ├── .env.example                three placeholder keys
│   ├── architecture.md             mermaid pipeline + sequence diagram, latency budget, component decisions
│   ├── evaluation-plan.md          WER methodology, 150-sample test corpus, ablation matrix
│   ├── typescript-proxy-example.ts skeleton TS proxy for iTranslate's TS team
│   └── sample-output.txt           captured terminal output from a real run
└── part2-spanglish/                production customer escalation
    ├── README.md                   bug summary, file index
    ├── SpanglishFixed.java         corrected Java client, every change inline `// FIX:` commented
    ├── customer-email.md           customer-facing reply with fix and scaling/privacy pointers
    ├── scaling-to-2000.md          staged rollout, bandwidth math, per-minute rate-limit framing
    ├── privacy-and-retention.md    conditional opt-out language, compliance posture, customer-side responsibilities
    ├── internal-engineering-summary.md   RCA confirming v3 service is fine, not a backend bug
    └── ooo-handoff.md              colleague handoff for the original engineer returning from OOO
```

## Triage order

I worked Spanglish first, iTranslate second. Production customer at risk takes precedence over a sales demo. The Loom video walks through the same order.

## How to read this in 5 minutes

1. Read this file (you are here).
2. Skim `part2-spanglish/README.md` and look at the three blocker fixes in `SpanglishFixed.java`.
3. Open `part1-itranslate/architecture.md`, look at the diagrams and the latency budget.
4. Watch the Loom (linked below) for the FDE-mindset narrative.

## How to run the demo locally

From `part1-itranslate/`:

```bash
cp .env.example .env       # then paste your AAI key (and optionally OpenAI / ElevenLabs)
pip install -r requirements.txt
python demo.py             # STT-only, the safe default
python demo.py --enable-translation --enable-tts --target-lang es   # full pipeline
```

See `part1-itranslate/README.md` for full options, accuracy levers, and Windows audio troubleshooting.

## Loom video

Walk-through of the bug fix and the demo, FDE-mindset narrative, ~4:30 total.

Link: https://www.loom.com/share/5ac9d46b29e14d35889b6de1cec0a986

## Notes for the reviewer

Honest disclaimers, in case they matter:

- I am applying as a candidate. The customer-facing email and the internal engineering summary are written as if I were already on the team handling the Spanglish escalation, because the take-home asks for that role-play.
- Privacy claims in `privacy-and-retention.md` were verified against AssemblyAI's live security, DPA, BAA, and retention pages. Anything I could not verify was softened to "available on request" rather than asserted.
- Scaling claims (no total concurrent cap, per-minute new-session rate limit, auto-grow at 70% utilization) match AssemblyAI's current public docs.

## Contact

Mario Cuevas
officialmariocuevas@gmail.com
github.com/mariostacksnqueues
