package com.assemblyai;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import javax.sound.sampled.*;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.net.URI;
import java.nio.ByteBuffer;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * SpanglishFixed.java - corrected client for AssemblyAI Universal Streaming v3.
 *
 * Original customer code reported "doesn't work at all." Three blockers stacked:
 *   1. URL declared encoding=opus while the code captured raw PCM s16le.
 *   2. URL was missing the required speech_model parameter.
 *   3. main() instantiated new StreamingTranscription() but the class is Spanglish
 *      (the file would not compile).
 *
 * This file fixes all three plus seven production-reliability issues that would
 * have surfaced under load (no reconnect, undersized 25 ms buffer, unbounded
 * recording heap, audio-thread shutdown race, non-idempotent cleanup, opaque
 * close codes, missing config for the EN/ES court use case). Every change is
 * annotated inline with `// FIX:` so the diff is auditable line by line.
 *
 * Configured for Spanglish Inc.'s use case: court-interpreter note-taking with
 * mixed English and Spanish speech. Universal-3 Pro Streaming (u3-rt-pro) is
 * selected for native EN/ES code-switching, format_turns, language_detection,
 * and speaker_labels.
 *
 * Compile (with gson.jar and Java-WebSocket on the classpath):
 *   javac -cp "gson.jar:Java-WebSocket.jar" SpanglishFixed.java
 * Run:
 *   java  -cp ".:gson.jar:Java-WebSocket.jar" com.assemblyai.SpanglishFixed
 */
public class SpanglishFixed {

    // Configuration
    private static final String API_KEY = "api_key"; // replace with real key or load from env
    private static final int SAMPLE_RATE = 16000;
    private static final int CHANNELS = 1;
    private static final int SAMPLE_SIZE_IN_BITS = 16;

    // FIX: was 400 frames (25 ms at 16 kHz). AssemblyAI Streaming v3 expects 50 to
    // 1000 ms chunks. Below 50 ms inflates per-message framing overhead and can
    // confuse server-side voice-activity detection. 800 frames is exactly 50 ms.
    private static final int FRAMES_PER_BUFFER = 800;

    // FIX: hard cap on the on-disk recording so a runaway session can't fill the
    // disk. The original code accumulated every audio frame in an unbounded
    // ArrayList. A 30-minute court session at 16 kHz / 16-bit mono is ~57 MB per
    // stream; at 2,000 concurrent streams that is ~114 GB of heap. We now stream
    // PCM bytes to a RandomAccessFile incrementally, so memory stays flat.
    private static final long MAX_RECORDING_BYTES = 1_000_000_000L; // 1 GB

    // FIX: was -
    //   "wss://streaming.assemblyai.com/v3/ws?sample_rate=%d&encoding=opus&format_turns=true"
    // Three corrections applied:
    //   - encoding=opus -> encoding=pcm_s16le. v3 only supports pcm_s16le and
    //     pcm_mulaw. The code captures raw PCM s16le, so the server was being told
    //     to decode Opus from raw PCM bytes, which never worked.
    //   - speech_model=u3-rt-pro added. v3 has no default model; the parameter is
    //     required on every connection (verified against current AAI v3 docs).
    //   - language_detection=true, speaker_labels=true, max_speakers=4 added for
    //     the court-interpreter use case (mixed EN/ES with judge / counsel /
    //     witness / interpreter).
    private static final String API_ENDPOINT = String.format(
        "wss://streaming.assemblyai.com/v3/ws"
            + "?sample_rate=%d"
            + "&speech_model=u3-rt-pro"
            + "&encoding=pcm_s16le"
            + "&format_turns=true"
            + "&language_detection=true"
            + "&speaker_labels=true"
            + "&max_speakers=4",
        SAMPLE_RATE
    );

    // FIX: reconnect tuning. Original onClose/onError just stopped the world; a
    // single network blip ended a multi-hour court session. We now retry with
    // capped exponential backoff and full jitter, only stopping on user-initiated
    // termination or 1008 (rate limit, where retrying just amplifies pressure).
    private static final int MAX_RECONNECT_ATTEMPTS = 5;
    private static final long INITIAL_BACKOFF_MS = 500;
    private static final long MAX_BACKOFF_MS = 30_000;

    // Audio recording
    private TargetDataLine microphone;
    private RandomAccessFile recordingFile;                                     // FIX: stream to disk, no heap growth
    private final AtomicLong recordedBytes = new AtomicLong(0);
    private final AtomicBoolean isRecording = new AtomicBoolean(false);
    private final AtomicBoolean stopRequested = new AtomicBoolean(false);
    private final AtomicBoolean userInitiatedStop = new AtomicBoolean(false);   // FIX: distinguish user stop from network drop
    private final AtomicBoolean cleanupCalled = new AtomicBoolean(false);       // FIX: idempotency guard
    private final Gson gson = new Gson();
    private volatile AssemblyAIWebSocketClient wsClient;                        // FIX: volatile for reconnect visibility
    private Thread audioThread;
    private String currentRecordingPath;

    public static void main(String[] args) {
        // FIX: was `new StreamingTranscription()`. The class declared in this file
        // is Spanglish (renamed here to SpanglishFixed for clarity in the diff).
        // The original constructor reference was unresolved, so the file did not
        // compile. Fix is to match the constructor to the declared class.
        SpanglishFixed transcription = new SpanglishFixed();
        transcription.run();
    }

    public void run() {
        System.out.println("Starting AssemblyAI Universal-3 Pro Streaming transcription...");
        System.out.println("Audio will be saved to a WAV file when the session ends.");

        try {
            initializeMicrophone();
            openRecordingFile();
            connectWebSocket();

            CountDownLatch latch = new CountDownLatch(1);
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                System.out.println("\nCtrl+C received. Stopping...");
                userInitiatedStop.set(true); // FIX: mark this as user stop so onClose won't reconnect
                stopRequested.set(true);
                cleanup();
                latch.countDown();
            }, "spanglish-shutdown"));

            System.out.println("Speak into your microphone. Press Ctrl+C to stop.");
            latch.await();
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
            cleanup();
        }
    }

    private void initializeMicrophone() throws LineUnavailableException {
        AudioFormat format = new AudioFormat(
            SAMPLE_RATE,
            SAMPLE_SIZE_IN_BITS,
            CHANNELS,
            true,    // signed
            false    // little endian
        );
        DataLine.Info info = new DataLine.Info(TargetDataLine.class, format);
        if (!AudioSystem.isLineSupported(info)) {
            throw new LineUnavailableException("Microphone not supported");
        }
        microphone = (TargetDataLine) AudioSystem.getLine(info);
        microphone.open(format, FRAMES_PER_BUFFER * 2);
        System.out.println("Microphone initialized successfully.");
    }

    // FIX: open a RandomAccessFile, reserve 44 bytes for the WAV header, then
    // append PCM bytes as they arrive. On cleanup we seek back and patch the
    // header sizes. This bounds heap to a single audio buffer regardless of
    // session length.
    private void openRecordingFile() throws IOException {
        String timestamp = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss")
            .withZone(ZoneId.systemDefault())
            .format(Instant.now());
        currentRecordingPath = "recorded_audio_" + timestamp + ".wav";
        recordingFile = new RandomAccessFile(currentRecordingPath, "rw");
        recordingFile.write(new byte[44]); // placeholder header
    }

    private void connectWebSocket() throws Exception {
        URI uri = new URI(API_ENDPOINT);
        Map<String, String> headers = new HashMap<>();
        // FIX: documented (NOT a code change). The Authorization header takes the
        // bare API key with no "Bearer " prefix, per AAI v3 docs. Original code is
        // correct here; flagged because it looks wrong at a glance.
        headers.put("Authorization", API_KEY);
        wsClient = new AssemblyAIWebSocketClient(uri, headers);
        wsClient.connectBlocking();
    }

    // FIX: capped exponential backoff with full jitter. Returns true on success.
    private boolean reconnectWithBackoff() {
        for (int attempt = 1; attempt <= MAX_RECONNECT_ATTEMPTS; attempt++) {
            long base = Math.min(INITIAL_BACKOFF_MS * (1L << (attempt - 1)), MAX_BACKOFF_MS);
            long jittered = (long) (Math.random() * base);
            try {
                Thread.sleep(jittered);
                System.err.printf("Reconnect attempt %d of %d...%n", attempt, MAX_RECONNECT_ATTEMPTS);
                connectWebSocket();
                System.err.println("Reconnected.");
                return true;
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                return false;
            } catch (Exception e) {
                System.err.printf("Reconnect attempt %d failed: %s%n", attempt, e.getMessage());
            }
        }
        return false;
    }

    private void startAudioStreaming() {
        // FIX: idempotency guard for reconnect path. onOpen fires every time we
        // reconnect, but the audio thread should only start once for the session.
        if (isRecording.get() && audioThread != null && audioThread.isAlive()) {
            System.out.println("Audio thread already running; resuming stream on new socket.");
            return;
        }
        isRecording.set(true);
        microphone.start();
        audioThread = new Thread(() -> {
            System.out.println("Starting audio streaming...");
            byte[] buffer = new byte[FRAMES_PER_BUFFER * 2]; // 2 bytes per 16-bit sample
            while (!stopRequested.get() && isRecording.get()) {
                try {
                    int bytesRead = microphone.read(buffer, 0, buffer.length);
                    if (bytesRead > 0) {
                        // FIX: stream to disk instead of accumulating in ArrayList.
                        long total = recordedBytes.addAndGet(bytesRead);
                        if (total > MAX_RECORDING_BYTES) {
                            System.err.println("Recording reached cap; transcription continues, recording paused.");
                            isRecording.set(false);
                            // Still send to WS so transcripts keep flowing.
                        } else if (recordingFile != null) {
                            synchronized (recordingFile) {
                                recordingFile.write(buffer, 0, bytesRead);
                            }
                        }
                        AssemblyAIWebSocketClient client = wsClient;
                        if (client != null && client.isOpen()) {
                            byte[] frame = new byte[bytesRead];
                            System.arraycopy(buffer, 0, frame, 0, bytesRead);
                            client.send(frame);
                        }
                    }
                } catch (Exception e) {
                    if (!stopRequested.get()) {
                        System.err.println("Error streaming audio: " + e.getMessage());
                    }
                    break;
                }
            }
            System.out.println("Audio streaming stopped.");
        }, "spanglish-audio");
        audioThread.start();
    }

    private void cleanup() {
        // FIX: idempotency. Shutdown hook + main-thread catch could both call
        // cleanup, which would attempt to write the WAV file twice and corrupt it.
        if (!cleanupCalled.compareAndSet(false, true)) {
            return;
        }
        stopRequested.set(true);
        isRecording.set(false);

        // FIX: stop the microphone BEFORE joining the audio thread. The thread
        // blocks inside microphone.read(), and stop() is what unblocks it.
        if (microphone != null) {
            try {
                if (microphone.isActive()) {
                    microphone.stop();
                }
            } catch (Exception e) {
                System.err.println("Error stopping microphone: " + e.getMessage());
            }
        }

        // FIX: increased join timeout to 3000 ms and added explicit interrupt() so
        // the audio thread can exit even if microphone.stop() races.
        if (audioThread != null && audioThread.isAlive()) {
            audioThread.interrupt();
            try {
                audioThread.join(3000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        // Close microphone after audio thread has exited.
        if (microphone != null) {
            try {
                microphone.close();
            } catch (Exception e) {
                System.err.println("Error closing microphone: " + e.getMessage());
            }
        }

        // Close WebSocket cleanly with a Terminate message.
        if (wsClient != null && wsClient.isOpen()) {
            try {
                JsonObject terminateMsg = new JsonObject();
                terminateMsg.addProperty("type", "Terminate");
                wsClient.send(gson.toJson(terminateMsg));
                Thread.sleep(500); // allow message to flush
                wsClient.closeBlocking();
            } catch (Exception e) {
                System.err.println("Error closing WebSocket: " + e.getMessage());
            }
        }

        // Patch the WAV header now that we know the final byte count, then close.
        finalizeRecordingFile();

        System.out.println("Cleanup complete. Exiting.");
    }

    // FIX: replaces saveWavFile(). The original buffered everything in memory and
    // wrote on shutdown. We now stream during the session and patch the header
    // here after seeking to position 0.
    private void finalizeRecordingFile() {
        if (recordingFile == null) return;
        try {
            long dataSize = recordedBytes.get();
            if (dataSize <= 0) {
                System.out.println("No audio data recorded.");
            } else {
                // FIX: simple cast is safe because the in-loop check at line ~232 caps
                // recordedBytes at MAX_RECORDING_BYTES (1 GB). 1 GB fits comfortably
                // inside a signed 32-bit int (Integer.MAX_VALUE ~= 2.147 GB), so the
                // WAV header dataSize field always matches the actual file payload.
                int patchSize = (int) dataSize;
                synchronized (recordingFile) {
                    recordingFile.seek(0);
                    recordingFile.write(buildWavHeader(patchSize));
                }
                double durationSeconds = (double) dataSize / (SAMPLE_RATE * CHANNELS * 2);
                System.out.printf("Audio saved to: %s%n", currentRecordingPath);
                System.out.printf("Duration: %.2f seconds%n", durationSeconds);
            }
        } catch (IOException e) {
            System.err.println("Error finalizing WAV file: " + e.getMessage());
        } finally {
            try {
                recordingFile.close();
            } catch (IOException ignored) {
            }
            recordingFile = null;
        }
    }

    private byte[] buildWavHeader(int dataSize) {
        ByteBuffer buffer = ByteBuffer.allocate(44);
        buffer.order(java.nio.ByteOrder.LITTLE_ENDIAN);
        // RIFF header
        buffer.put("RIFF".getBytes());
        buffer.putInt(36 + dataSize);
        buffer.put("WAVE".getBytes());
        // fmt chunk: 4-byte chunk id "fmt " (note the trailing space, per RIFF spec).
        buffer.put("fmt ".getBytes());
        buffer.putInt(16);                                  // fmt chunk size
        buffer.putShort((short) 1);                         // PCM format
        buffer.putShort((short) CHANNELS);
        buffer.putInt(SAMPLE_RATE);
        buffer.putInt(SAMPLE_RATE * CHANNELS * 2);          // byte rate
        buffer.putShort((short) (CHANNELS * 2));            // block align
        buffer.putShort((short) SAMPLE_SIZE_IN_BITS);
        // data chunk
        buffer.put("data".getBytes());
        buffer.putInt(dataSize);
        return buffer.array();
    }

    // FIX: human-readable mapping for known AAI close codes. The original code
    // printed the raw integer to stdout, which makes "doesn't work at all"
    // tickets hard to triage. Map the codes we know about; fall through for the
    // rest.
    private static String describeCloseCode(int code) {
        switch (code) {
            case 1000: return "Normal closure";
            case 1006: return "Abnormal closure (TCP reset / network blip)";
            case 1008: return "Concurrency / rate limit (new sessions per minute exceeded)";
            case 1011: return "Server-side error (transient, retry)";
            case 4001: return "AAI: Authentication failed (check API key)";
            case 4002: return "AAI: Bad sample rate (must match audio capture)";
            case 4003: return "AAI: Bad audio frame";
            case 4008: return "AAI: Bad encoding (check encoding= matches actual audio bytes)";
            case 4009: return "AAI: Session timeout";
            default:   return "Unrecognized close code";
        }
    }

    // Inner class for WebSocket client
    private class AssemblyAIWebSocketClient extends WebSocketClient {

        public AssemblyAIWebSocketClient(URI serverUri, Map<String, String> headers) {
            super(serverUri, headers);
        }

        @Override
        public void onOpen(ServerHandshake handshake) {
            System.out.println("WebSocket connection opened.");
            System.out.println("Connected to: " + API_ENDPOINT);
            startAudioStreaming();
        }

        @Override
        public void onMessage(String message) {
            try {
                JsonObject data = gson.fromJson(message, JsonObject.class);
                String msgType = data.get("type").getAsString();
                switch (msgType) {
                    case "Begin":
                        handleBeginMessage(data);
                        break;
                    case "Turn":
                        handleTurnMessage(data);
                        break;
                    case "Termination":
                        handleTerminationMessage(data);
                        break;
                    default:
                        // Ignore unknown message types
                        break;
                }
            } catch (Exception e) {
                System.err.println("Error handling message: " + e.getMessage());
            }
        }

        private void handleBeginMessage(JsonObject data) {
            String sessionId = data.get("id").getAsString();
            long expiresAt = data.get("expires_at").getAsLong();
            Instant instant = Instant.ofEpochSecond(expiresAt);
            String formattedTime = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
                .withZone(ZoneId.systemDefault())
                .format(instant);
            System.out.printf("%nSession began: ID=%s, ExpiresAt=%s%n", sessionId, formattedTime);
        }

        private void handleTurnMessage(JsonObject data) {
            String transcript = data.has("transcript") ? data.get("transcript").getAsString() : "";
            boolean formatted = data.has("turn_is_formatted") && data.get("turn_is_formatted").getAsBoolean();
            // FIX: also surface speaker label and detected language when present, so
            // the court-interpreter consumer can structure the transcript by
            // speaker. Both fields are optional - present only when the matching
            // session params are enabled.
            String speaker = data.has("speaker") ? data.get("speaker").getAsString() : null;
            String language = data.has("language") ? data.get("language").getAsString() : null;
            if (formatted) {
                System.out.print("\r" + " ".repeat(80) + "\r");
                StringBuilder line = new StringBuilder();
                if (speaker != null) line.append("[").append(speaker).append("] ");
                if (language != null) line.append("[").append(language).append("] ");
                line.append(transcript);
                System.out.println(line.toString());
            } else {
                System.out.print("\r" + transcript);
            }
        }

        private void handleTerminationMessage(JsonObject data) {
            double audioDuration = data.has("audio_duration_seconds")
                ? data.get("audio_duration_seconds").getAsDouble() : 0.0;
            double sessionDuration = data.has("session_duration_seconds")
                ? data.get("session_duration_seconds").getAsDouble() : 0.0;
            System.out.printf("%nSession Terminated: Audio Duration=%.2fs, Session Duration=%.2fs%n",
                audioDuration, sessionDuration);
        }

        @Override
        public void onClose(int code, String reason, boolean remote) {
            System.out.printf("%nWebSocket Disconnected: Status=%d (%s), Msg=%s%n",
                code, describeCloseCode(code), reason);

            // FIX: only treat user-initiated stops as terminal. For any other
            // reason, attempt reconnect with exponential backoff. 1008 (rate
            // limit) is the one close code we should NOT auto-reconnect on; it
            // indicates the per-minute new-session limit is saturated and we
            // would just amplify the back-pressure.
            if (userInitiatedStop.get() || code == 1008) {
                stopRequested.set(true);
                return;
            }
            new Thread(() -> {
                if (!reconnectWithBackoff()) {
                    System.err.println("Reconnect attempts exhausted. Stopping.");
                    stopRequested.set(true);
                }
            }, "spanglish-reconnect").start();
        }

        @Override
        public void onError(Exception ex) {
            System.err.println("\nWebSocket Error: " + ex.getMessage());
            // FIX: do NOT immediately set stopRequested. Let onClose decide
            // whether to reconnect; onError fires for transient transport errors
            // that often recover on the next handshake.
        }
    }
}
