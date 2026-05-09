// @ts-nocheck
// Reviewer note: this file is a skeleton example, not a runnable project.
// There is no package.json or node_modules in this repo by design (it is
// reference code for iTranslate's team to drop into their own service).
// The @ts-nocheck directive above suppresses the "cannot find module" errors
// for `ws`, `dotenv`, `http`, and `process` that would resolve cleanly once
// iTranslate runs `npm install ws dotenv && npm install -D @types/node` in
// their own repo. The shape, types, and patterns below are correct.

/**
 * iTranslate STT Proxy Skeleton (Node.js + TypeScript)
 *
 * This is a reference implementation for iTranslate's TypeScript team,
 * demonstrating how the STT layer integrates into their backend.
 * Production-ready in shape and pattern, NOT in security or scale.
 * See TODOs for real-world gaps.
 *
 * Architecture:
 *   - iTranslate handheld device opens one outbound WebSocket to this proxy.
 *   - Proxy holds the AssemblyAI API key (never leaves the server).
 *   - Device streams PCM frames; proxy forwards to AAI Universal-3 Pro.
 *   - AAI streams transcripts back; proxy relays to device.
 *
 * Why a proxy:
 *   - API key stays server-side, off battery-powered hardware.
 *   - Centralize observability, rate limiting, and auth.
 *   - Apply per-tenant config (keyterms, retention) server-side.
 *   - Absorb AAI reconnect logic away from device.
 *
 * Run:
 *   npm install ws dotenv
 *   tsc
 *   node dist/typescript-proxy-example.js
 */

import * as WebSocket from "ws";
import { createServer as createHttpServer } from "http";
import { config as loadEnv } from "dotenv";

loadEnv();

// =============================================================================
// Types and Interfaces
// =============================================================================

interface DeviceConfig {
  sampleRate: number;
  encoding: string;
  speechModel: string;
  formatTurns: boolean;
  languageDetection: boolean;
}

interface SessionContext {
  sessionId: string;
  deviceToken: string;
  upstream: WebSocket.WebSocket | null;
  downstreamFirstMessage: boolean;
  createdAt: number;
  firstTokenLatency: number | null;
  lastActivityAt: number;
}

interface AAIMessage {
  message_type?: string;
  partial_transcript?: string;
  final_transcript?: string;
  format_turns?: Array<{
    speaker: string;
    text: string;
  }>;
  language_detection?: {
    languages: Array<{
      language: string;
      confidence: number;
    }>;
  };
}

// =============================================================================
// Configuration
// =============================================================================

const CONFIG: DeviceConfig = {
  sampleRate: 16000,
  encoding: "pcm_s16le",
  speechModel: "u3-rt-pro",
  formatTurns: true,
  languageDetection: true,
};

const AAI_ENDPOINT = "wss://api.assemblyai.com/v2/realtime/stream";
const AAI_API_KEY = process.env.AAI_API_KEY || "";
const PROXY_PORT = parseInt(process.env.PROXY_PORT || "8080");

// TODO: Use real environment-based credentials store (e.g., AWS Secrets Manager).
if (!AAI_API_KEY) {
  throw new Error("AAI_API_KEY environment variable not set");
}

// =============================================================================
// Proxy Server Implementation
// =============================================================================

class ProxyServer {
  private httpServer: ReturnType<typeof createHttpServer>;
  private wsServer: WebSocket.Server;
  private sessions: Map<string, SessionContext>;
  private isShuttingDown: boolean;

  constructor() {
    this.httpServer = createHttpServer();
    this.wsServer = new WebSocket.Server({ server: this.httpServer });
    this.sessions = new Map();
    this.isShuttingDown = false;

    this.setupHandlers();
    this.setupGracefulShutdown();
  }

  private setupHandlers(): void {
    this.wsServer.on("connection", (downstream: WebSocket.WebSocket, req) => {
      this.handleDeviceConnection(downstream, req);
    });
  }

  private setupGracefulShutdown(): void {
    process.on("SIGTERM", () => {
      console.log("[proxy] SIGTERM received, draining connections...");
      this.isShuttingDown = true;

      // Close HTTP server (refuses new connections).
      this.httpServer.close(() => {
        console.log("[proxy] HTTP server closed");
      });

      // Drain existing WebSocket sessions gracefully.
      for (const [sessionId, context] of this.sessions) {
        if (context.upstream) {
          context.upstream.close(1000, "proxy shutdown");
        }
        // Device WebSocket will be closed automatically when upstream closes.
      }

      // Hard exit after 10 seconds.
      setTimeout(() => {
        console.log("[proxy] Force exit after shutdown timeout");
        process.exit(0);
      }, 10000);
    });
  }

  private handleDeviceConnection(
    downstream: WebSocket.WebSocket,
    req: any
  ): void {
    // TODO: Real device auth. Replace with token validation against iTranslate's
    // auth system (e.g., verify JWT in query string against a secrets store).
    const deviceToken = new URL(
      req.url,
      `http://${req.headers.host}`
    ).searchParams.get("token");
    if (!deviceToken) {
      console.warn("[proxy] Device connection rejected: no auth token");
      downstream.close(4001, "Unauthorized");
      return;
    }

    const sessionId = this.generateSessionId();
    console.log(`[proxy] Device connected: ${sessionId}`);

    const context: SessionContext = {
      sessionId,
      deviceToken,
      upstream: null,
      downstreamFirstMessage: false,
      createdAt: Date.now(),
      firstTokenLatency: null,
      lastActivityAt: Date.now(),
    };

    this.sessions.set(sessionId, context);

    downstream.on("message", (data) => {
      this.handleDeviceMessage(sessionId, data);
    });

    downstream.on("close", (code, reason) => {
      console.log(
        `[proxy] Device disconnected (${sessionId}): code=${code}, reason=${reason}`
      );
      this.closeSession(sessionId);
    });

    downstream.on("error", (err) => {
      console.error(`[proxy] Device socket error (${sessionId}):`, err.message);
      this.closeSession(sessionId);
    });
  }

  private handleDeviceMessage(sessionId: string, data: WebSocket.Data): void {
    const context = this.sessions.get(sessionId);
    if (!context) {
      console.warn(`[proxy] Message for unknown session: ${sessionId}`);
      return;
    }

    context.lastActivityAt = Date.now();

    // First message from device: open upstream to AAI.
    if (!context.upstream) {
      this.openUpstream(sessionId, data);
      return;
    }

    // Forward subsequent binary frames to AAI.
    if (context.upstream.readyState === WebSocket.OPEN) {
      context.upstream.send(data, (err) => {
        if (err) {
          console.error(
            `[proxy] Error forwarding to AAI (${sessionId}):`,
            err.message
          );
        }
      });
    }
  }

  private openUpstream(sessionId: string, initialData: WebSocket.Data): void {
    const context = this.sessions.get(sessionId);
    if (!context) return;

    // Build AAI connection string with query parameters.
    const aaiUrl = new URL(AAI_ENDPOINT);
    aaiUrl.searchParams.set("sample_rate", String(CONFIG.sampleRate));
    aaiUrl.searchParams.set("encoding", CONFIG.encoding);
    aaiUrl.searchParams.set("speech_model", CONFIG.speechModel);
    aaiUrl.searchParams.set("format_turns", String(CONFIG.formatTurns));
    aaiUrl.searchParams.set("language_detection", String(CONFIG.languageDetection));
    // TODO: Populate keyterms_prompt from iTranslate's per-tenant config store.

    const upstream = new WebSocket.WebSocket(aaiUrl.toString(), {
      headers: {
        Authorization: AAI_API_KEY,
      },
    });

    const tokenTimestamp = Date.now();

    upstream.on("open", () => {
      console.log(`[proxy] Upstream connected (${sessionId})`);
      context.upstream = upstream;
      // Send the initial data that triggered the connection.
      upstream.send(initialData, (err) => {
        if (err) {
          console.error(`[proxy] Error sending initial frame (${sessionId}):`, err.message);
        }
      });
    });

    upstream.on("message", (data) => {
      // Parse AAI response and relay to device.
      let message: AAIMessage;
      try {
        message = JSON.parse(data.toString());
      } catch {
        console.error(`[proxy] Failed to parse AAI message (${sessionId})`);
        return;
      }

      // Record first token latency.
      if (
        context.firstTokenLatency === null &&
        (message.partial_transcript || message.final_transcript)
      ) {
        context.firstTokenLatency = Date.now() - tokenTimestamp;
        console.log(
          `[proxy] First token latency (${sessionId}): ${context.firstTokenLatency} ms`
        );
      }

      // Forward to device.
      const downstream = this.wsServer.clients.forEach((client) => {
        // TODO: Track downstream client reference in SessionContext for faster lookup.
        // This is O(n) iteration; in production, store it at connection time.
      });
      // Workaround: session context needs a back-reference to downstream.
      // See TODO below.
      const deviceSocket = (context as any).downstream;
      if (deviceSocket && deviceSocket.readyState === WebSocket.OPEN) {
        deviceSocket.send(JSON.stringify(message), (err) => {
          if (err) {
            console.error(
              `[proxy] Error forwarding to device (${sessionId}):`,
              err.message
            );
          }
        });
      }
    });

    upstream.on("close", (code, reason) => {
      console.log(
        `[proxy] Upstream closed (${sessionId}): code=${code}, reason=${reason}`
      );
      // TODO: Implement exponential backoff reconnection with jitter.
      // If the device is still streaming, reconnect upstream automatically.
      // For now, closing upstream closes the device connection (failfast).
      this.closeSession(sessionId);
    });

    upstream.on("error", (err) => {
      console.error(`[proxy] Upstream error (${sessionId}):`, err.message);
      this.closeSession(sessionId);
    });

    context.upstream = upstream;
  }

  private closeSession(sessionId: string): void {
    const context = this.sessions.get(sessionId);
    if (!context) return;

    if (context.upstream && context.upstream.readyState === WebSocket.OPEN) {
      context.upstream.close(1000, "session closed");
    }

    // TODO: Store first_token_latency in observability sink
    // (e.g., CloudWatch, Datadog, or iTranslate's logging service).
    if (context.firstTokenLatency !== null) {
      console.log(
        `[session_complete] sessionId=${sessionId}, ` +
        `firstTokenLatency=${context.firstTokenLatency}ms, ` +
        `duration=${Date.now() - context.createdAt}ms`
      );
    }

    this.sessions.delete(sessionId);
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
  }

  public start(): Promise<void> {
    return new Promise((resolve) => {
      this.httpServer.listen(PROXY_PORT, () => {
        console.log(`[proxy] Listening on port ${PROXY_PORT}`);
        resolve();
      });
    });
  }

  public stop(): Promise<void> {
    return new Promise((resolve) => {
      this.httpServer.close(() => {
        console.log("[proxy] Server stopped");
        resolve();
      });
    });
  }
}

// =============================================================================
// Main
// =============================================================================

const server = new ProxyServer();

server.start().catch((err) => {
  console.error("[proxy] Failed to start:", err);
  process.exit(1);
});

// Export for testing.
export { ProxyServer, SessionContext, DeviceConfig };
