import type { OpenHerEvent } from "../types/openher";
import { normalizeBaseUrl } from "./openherClient";
import { buildDemoMemoryPayload, buildDemoScenarioPayload, buildDemoTimeJumpPayload, type DemoMemory } from "../demo/catalog";

export interface SocketHandlers {
  onEvent: (event: OpenHerEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (message: string) => void;
}

export class OpenHerSocket {
  private ws: WebSocket | null = null;
  private sessionId: string | null = null;
  private reconnectTimer = 0;

  constructor(
    private readonly baseUrl: string,
    private readonly clientId: string,
    private readonly handlers: SocketHandlers,
  ) {}

  connect(): void {
    this.disconnect(false);
    const wsBase = normalizeBaseUrl(this.baseUrl)
      .replace(/^http:\/\//, "ws://")
      .replace(/^https:\/\//, "wss://");
    this.ws = new WebSocket(`${wsBase}/ws/chat`);

    this.ws.addEventListener("open", () => {
      this.handlers.onOpen?.();
      this.sendRaw({ type: "handshake", client_id: this.clientId });
    });

    this.ws.addEventListener("message", (message) => {
      try {
        const raw = JSON.parse(String(message.data)) as { type?: string; session_id?: unknown };
        const event = normalizeEvent(raw);
        if (typeof raw.session_id === "string") {
          this.sessionId = raw.session_id;
        }
        this.handlers.onEvent(event);
      } catch (error) {
        this.handlers.onError?.(`Invalid WebSocket payload: ${String(error)}`);
      }
    });

    this.ws.addEventListener("close", () => {
      this.handlers.onClose?.();
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = window.setTimeout(() => this.connect(), 3000);
    });

    this.ws.addEventListener("error", () => {
      this.handlers.onError?.("WebSocket connection error");
    });
  }

  disconnect(allowCloseHandler = true): void {
    window.clearTimeout(this.reconnectTimer);
    if (!this.ws) return;
    const socket = this.ws;
    this.ws = null;
    if (!allowCloseHandler) {
      socket.onclose = null;
    }
    socket.close();
  }

  sendChat(content: string, personaId: string, userName: string | null, debug: boolean, greeting?: string): void {
    this.sendRaw({
      type: "chat",
      content,
      persona_id: personaId,
      client_id: this.clientId,
      user_name: userName || undefined,
      session_id: this.sessionId || undefined,
      debug,
      greeting,
    });
  }

  sendTyping(active: boolean): void {
    this.sendRaw({ type: "typing", active });
  }

  switchPersona(personaId: string): void {
    this.sessionId = null;
    this.sendRaw({
      type: "switch_persona",
      persona_id: personaId,
      client_id: this.clientId,
    });
  }

  requestStatus(): void {
    this.sendRaw({ type: "status" });
  }

  sendDemoTimeJump(hours: number): void {
    this.sendRaw(buildDemoTimeJumpPayload(hours));
  }

  sendDemoScenario(scenarioId: string): void {
    this.sendRaw(buildDemoScenarioPayload(scenarioId));
  }

  sendDemoInject(overrides: Record<string, unknown> = {}): void {
    this.sendRaw({ type: "demo_inject", overrides });
  }

  sendDemoPresets(): void {
    this.sendRaw({ type: "demo_presets" });
  }

  sendDemoForceProactive(): void {
    this.sendRaw({ type: "demo_force_proactive" });
  }

  sendDemoInjectMemory(memory: DemoMemory, personaId: string): void {
    this.sendRaw(buildDemoMemoryPayload(memory, personaId, this.clientId));
  }

  private sendRaw(payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.handlers.onError?.("WebSocket is not connected");
      return;
    }
    this.ws.send(JSON.stringify(payload));
  }
}

function normalizeEvent(raw: { type?: string; [key: string]: unknown }): OpenHerEvent {
  switch (raw.type) {
    case "chat_start":
    case "chat_chunk":
    case "chat_end":
    case "silence":
    case "proactive":
    case "tts_audio":
    case "error":
    case "persona_switched":
    case "demo_state":
    case "demo_memory":
    case "demo_presets":
    case "status":
      return raw as OpenHerEvent;
    default:
      return { type: "unknown", raw };
  }
}
