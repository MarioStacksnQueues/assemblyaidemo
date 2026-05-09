# Evaluation Plan: Measuring STT Accuracy Gains for iTranslate

## Why Measure

Translation quality is bottlenecked by speech-to-text accuracy. Every word substitution or phrase fragment in the source-language transcript cascades into a corresponding error in the target translation. By quantifying Word Error Rate (WER) on the transcription layer, iTranslate can isolate and measure the most high-leverage component of the translation pipeline. This evaluation establishes a numerical baseline against which all STT improvements are judged, preventing costly optimization cycles in the translation or TTS layers that cannot compensate for upstream transcription failures.

## What to Measure

| Metric | Definition | Target |
|--------|-----------|--------|
| **Word Error Rate (WER)** | Levenshtein distance between hypothesis and ground-truth transcript, normalized by reference length. Standard speech-recognition metric. | < 8% on English-only conversational speech; < 12% on English/Spanish code-switching passages. |
| **Time to First Partial** | Wall-clock milliseconds from speech onset to first `partial_transcript` event from AssemblyAI. Reflects how quickly the model begins emitting hypotheses. | < 200 ms on standard US WiFi (latency 20-40 ms). |
| **Time to Final Transcript** | Elapsed milliseconds from speech end (silence threshold met) to `final_transcript` and `format_turns` completion event, ready for downstream TTS. | < 500 ms on 16 kHz PCM stream. |
| **Code-switching Language Detection Accuracy** | Percentage of word-level language boundaries (e.g., Spanish adjective modifying English noun) correctly tagged in `language_detection.languages` array. Measured against hand-labeled reference. | 90%+ on a balanced bilingual corpus. |
| **Proper-Noun Recall** | Percentage of in-vocabulary proper nouns (place names, brand names, person names) correctly transcribed when `keyterms_prompt` is populated with the term list. Baseline recall without keyterms for comparison. | 95%+ recall for terms in keyterms list; establish baseline (expected 60-70%) without list to quantify keyterms lift. |
| **End-of-Turn Correctness** | Percentage of true conversational turns that AssemblyAI `format_turns` correctly demarcates as distinct turn boundaries, without premature cutoffs or excessive merges across distinct speakers/pauses. | 95%+ on multi-turn conversational audio. |

## Test Corpus Design

Assemble a balanced test corpus of 150 audio samples with reference transcripts (ground truth) and human-verified language labels:

| Sample Type | Count | Characteristics | Example |
|------------|-------|-----------------|---------|
| English-only conversational | 50 | Tourist/traveler speech patterns: restaurant ordering, hotel check-in, asking directions, informal complaints, casual greetings. Normal prosody, varying speaker age/accent. | "I'd like a table for two near the window, please. Do you have any gluten-free options?" |
| English/Spanish code-switching | 50 | Realistic bilingual utterances from travel and service contexts, with switches at phrase or clause boundaries. | "Vamos al parking lot, and then I'll meet you adentro in like five minutes, okay?" |
| Proper-noun dense | 25 | High density of place names (cities, landmarks, streets), brand names (hotel chains, restaurants), and person names. | "I'm staying at the Marriott on Paseo de la Reforma near Chapultepec. Can you call Miguel?" |
| Noisy environment | 25 | Recorded in realistic challenging conditions: car interior (engine/road noise), restaurant (background chatter/music), outdoor (wind, street noise). | Same utterances as English-only set, re-recorded in noisy contexts. |

**Corpus assembly SOP:** Use iTranslate's internal content library or hire 3-5 native bilingual speakers to record samples. Obtain reference transcripts by manual transcription (two independent annotators, adjudicate disagreements). For language detection, assign each word a ground-truth language label using a simple convention: predominant language of the word, or "code-switch" if morphologically or syntactically hybrid.

## How to Run the Evaluation

1. **Provision a test AAI account** opted out of Personally Identifiable Information and model training programs. This ensures evaluation audio does not enter model improvement data.

2. **Stream each of the 150 samples** through the demo.py pipeline with these parameters:
   - `--source-lang auto` (universal-3-pro detects language)
   - `format_turns=true` (enables turn formatting)
   - `language_detection=true` (populates language tags)
   - `keyterms_prompt` populated with the proper-noun list from the 25 proper-noun-dense samples (run once with; run baseline without)

3. **Capture outputs** for each sample:
   - Final transcript text (from `final_transcript` event)
   - Language labels per word (from `language_detection.languages`)
   - Timestamp of first `partial_transcript` event (relative to stream start)
   - Timestamp of final event (relative to speech end)
   - Formatted turns JSON (from `format_turns`)

4. **Compute WER** using `jiwer` Python package or equivalent TypeScript library. For each sample: `wer(reference=ground_truth_text, hypothesis=hypothesis_text)`. Aggregate by sample type.

5. **Compute latency percentiles** on "time to first partial" and "time to final": compute p50, p95, p99 across all samples. Segment by environment (clean, restaurant, car, outdoor) to identify environmental cost.

6. **Tag each sample** with environment condition and report WER stratified by environment. This reveals whether the model's accuracy degrades under noise or whether the device's audio capture AGC is the bottleneck.

## Baselines and Ablations

Run the evaluation against four configurations in priority order:

| Configuration | Speech Model | Levers | Purpose |
|--------------|--------------|--------|---------|
| **Full stack** | `u3-rt-pro` | `format_turns=true`, `language_detection=true`, `keyterms_prompt` populated | Represents iTranslate's best-case scenario with all AssemblyAI features. |
| **No keyterms** | `u3-rt-pro` | `format_turns=true`, `language_detection=true`, keyterms empty | Isolate keyterms effectiveness; control for model baseline. |
| **Plain streaming** | `u3-rt-pro` | Default (no special params) | Baseline model without formatting or detection. |
| **Non-Pro baseline** | `universal-streaming` | Default | Competitive baseline; what iTranslate would get with a cheaper tier. |

The gap between row 1 and row 4 quantifies iTranslate's accuracy budget for the full technology stack. The gap between rows 2 and 3 isolates the value of format_turns and language_detection. The gap between rows 1 and 2 isolates keyterms ROI.

## What "Good" Looks Like for iTranslate

A relative WER improvement of 15-25% (full stack vs. plain) is strong evidence that AssemblyAI's levers are worth integrating. Absolute WER under 10% on the English-only conversational subset is acceptable for a travel translation device. However, real device traffic differs from a controlled test corpus: speakers will talk faster, use domain-specific jargon, and the device's microphone and AGC settings will introduce artifacts absent from clean recordings.

If evaluation results undershoot targets, do not blame the API. First, loop back to iTranslate's hardware team: ask them to analyze the device's microphone frequency response, AGC behavior, and noise suppression settings. Many STT accuracy failures are rooted in pre-processing at the mic, not the speech model.

## Cost of Running the Evaluation

Streaming 150 samples at an average of 4 seconds each (600 seconds = 10 minutes total audio) costs approximately $0.15 per hour of streaming at current AssemblyAI list pricing, yielding < $0.05 per full evaluation run. This evaluation is repeated (baseline, intermediate, final) for less than $0.25 in API cost. Note: this budget covers STT only. Translation and TTS engines are separate measurement domains and not included in this plan.
