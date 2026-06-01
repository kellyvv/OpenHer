export type AppPhase = "discovery" | "awakening" | "conversation";

export type MessageRole = "user" | "assistant" | "system";

export type SendStatus = "sending" | "sent" | "failed";

export interface Persona {
  persona_id: string;
  name: string;
  name_zh?: string | null;
  age?: number | null;
  gender?: string | null;
  mbti?: string | null;
  tags: string[];
  tags_zh?: string[];
  description?: string | null;
  avatar_url?: string | null;
  has_front: boolean;
  has_awakening_video: boolean;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  modality: string;
  imageUrl?: string | null;
  audioUrl?: string | null;
  timestamp: number;
  sendStatus?: SendStatus;
  engineStatus?: EngineStatus | null;
  proactive?: boolean;
}

export interface EngineStatus {
  dominant_drive?: string;
  temperature?: number;
  frustration?: number;
  modality?: string;
  turn_count?: number;
  last_reward?: number;
  personal_memories?: number;
  relationship?: {
    depth?: number;
    trust?: number;
    valence?: number;
  };
  drive_state?: Record<string, number>;
  debug?: unknown;
}

export interface EngineDebugState {
  input_vector?: number[];
  hidden_activations?: number[];
  signals?: Record<string, number>;
  context_vector?: Record<string, number>;
  drive_state?: Record<string, number>;
  drive_baseline?: Record<string, number>;
  frustration?: number | Record<string, number>;
  temperature?: number;
  monologue?: string;
  style_recall?: Array<{ text: string; distance: number; mass?: number }>;
  relationship?: Record<string, number>;
  reward?: number;
  age?: number;
  turn_count?: number;
  phase_transition?: boolean;
  total_frustration?: number;
}

export interface DemoSnapshot {
  drive_state: Record<string, number>;
  drive_baseline?: Record<string, number>;
  frustration: Record<string, number>;
  temperature: number;
  total_frustration?: number;
  proactive_fired?: boolean;
  proactive_reply?: string;
}

export interface StatusResponse {
  name: string;
  version: string;
  engine: string;
  status: string;
  personas: string[];
  active_sessions: number;
}

export interface HistoryMessage {
  id: number;
  role: MessageRole;
  content: string;
  modality?: string;
  image_url?: string | null;
  created_at?: number;
  timestamp?: string;
}

export interface PersonasResponse {
  personas: Persona[];
}

export interface HistoryResponse {
  messages: HistoryMessage[];
  total: number;
}

export type OpenHerEvent =
  | { type: "chat_start"; session_id?: string; user_content?: string }
  | { type: "chat_chunk"; content: string }
  | ({ type: "chat_end"; reply?: string; image_url?: string | null; proactive?: boolean } & EngineStatus)
  | ({ type: "silence"; session_id?: string } & EngineStatus)
  | { type: "proactive"; content: string; modality?: string }
  | { type: "tts_audio"; audio: string; format?: string }
  | { type: "error"; content: string }
  | { type: "persona_switched"; session_id?: string; persona?: string }
  | ({ type: "demo_state" } & DemoSnapshot)
  | { type: "demo_memory"; content?: string; category?: string; ok?: boolean; [key: string]: unknown }
  | { type: "demo_presets"; presets?: Array<{ label: string; message: string }>; scenarios?: Record<string, unknown> }
  | ({ type: "status" } & EngineStatus)
  | { type: "unknown"; raw: unknown };
