Subject: Spanglish streaming fixed + path to 2,000 concurrent

---

Hi {{first_name}},

Found it. The good news is your v3 integration logic is solid. Your message protocol handling, the Begin/Turn/Termination event flow, the clean teardown with `{"type":"Terminate"}`, all of it is correct. The blockage was three configuration-side issues on the client, not the service.

Here's what was happening:

1. **Audio encoding mismatch.** Your URL had `encoding=opus`, but your code is reading raw 16-bit signed little-endian PCM from the microphone. v3 only supports `pcm_s16le` (the default) and `pcm_mulaw`. The server couldn't decode what it was receiving. Changing the encoding parameter to match your actual audio format unblocks this.

2. **Missing speech_model.** v3 requires an explicit speech model parameter on every connection. No default. For your bilingual EN/ES court use case the right value is `&speech_model=u3-rt-pro` (Universal-3 Pro Streaming): native code-switching, sub-300 ms latency, and supports `language_detection` and `speaker_labels` so you can structure the transcript by speaker out of the box. Without `speech_model`, the session fails to initialize.

3. **Class name.** Minor but blocking: your main instantiates `new StreamingTranscription()` but the class is declared `public class Spanglish`. Rename the instantiation to match.

I've attached **SpanglishFixed.java** with all three fixed. The structure stays exactly the same: just the config and one class name change.

On the two things you asked about:

**Scaling to 2,000 concurrent:** We don't cap total concurrent streams on the service side. The constraint is per-minute new sessions, which auto-grows when you're actually utilizing capacity. See **scaling-to-2000.md** for the staged rollout approach. Loop in your CSM about a week before launch; they can request the per-minute new-session limit be pre-warmed for your expected traffic shape. With the staged ramp, 2,000 is well within range.

**Data privacy and retention:** Full answer in **privacy-and-retention.md**. Headline: with the model-improvement opt-out on file, AssemblyAI offers zero data retention of audio and transcripts on Streaming. Some operational metadata (request IDs, byte counts, timestamps) stays for billing and abuse detection. For court proceedings where data sensitivity matters, the right setup is a signed DPA and opt-out on file. If any session might touch PHI, loop in your CSM to scope a BAA. This is a strength for your use case. You get production-grade transcription without data liability.

Happy to jump on a 30-min walkthrough this week if your CSM can set it up. That'll de-risk the launch.

Thanks for catching this and for the patience while the original engineer was out.

---

Mario Cuevas  
Applied AI Engineering  
AssemblyAI
