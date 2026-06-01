import type { DemoSnapshot, EngineDebugState } from "../types/openher";

type JsonRecord = Record<string, unknown>;

const MEMORY_KEYWORDS = ["美式", "团子", "跑步"];

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : null;
}

function asNumberRecord(value: unknown): Record<string, number> | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const entries = Object.entries(record)
    .map(([key, item]) => [key, typeof item === "number" ? item : Number(item)] as const)
    .filter(([, item]) => Number.isFinite(item));
  return entries.length ? Object.fromEntries(entries) : undefined;
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

export function extractEngineDebugState(payload: JsonRecord): EngineDebugState | null {
  const debug = asRecord(payload.debug) ?? payload;
  if (!debug) return null;

  const state: EngineDebugState = {
    ...debug,
    signals: asNumberRecord(debug.signals),
    context_vector: asNumberRecord(debug.context_vector),
    drive_state: asNumberRecord(debug.drive_state),
    drive_baseline: asNumberRecord(debug.drive_baseline),
    relationship: asNumberRecord(debug.relationship) ?? asNumberRecord(payload.relationship),
    temperature: asNumber(debug.temperature) ?? asNumber(payload.temperature),
    reward: asNumber(debug.reward) ?? asNumber(payload.last_reward),
    turn_count: asNumber(debug.turn_count) ?? asNumber(payload.turn_count),
    total_frustration: asNumber(debug.total_frustration),
  };

  if (typeof debug.monologue === "string") state.monologue = debug.monologue;
  if (typeof debug.frustration === "number") state.frustration = debug.frustration;
  if (Array.isArray(debug.input_vector)) state.input_vector = debug.input_vector.map(Number).filter(Number.isFinite);
  if (Array.isArray(debug.hidden_activations)) state.hidden_activations = debug.hidden_activations.map(Number).filter(Number.isFinite);
  if (Array.isArray(debug.style_recall)) state.style_recall = debug.style_recall as EngineDebugState["style_recall"];
  if (typeof debug.phase_transition === "boolean") state.phase_transition = debug.phase_transition;

  const frustrationByDrive = asNumberRecord(debug.frustration);
  if (frustrationByDrive) {
    state.frustration = frustrationByDrive;
    state.total_frustration = state.total_frustration ?? Object.values(frustrationByDrive).reduce((sum, item) => sum + item, 0);
  }

  return state;
}

export function extractDemoSnapshot(payload: JsonRecord): DemoSnapshot | null {
  const source = asRecord(payload.debug) ?? payload;
  const driveState = asNumberRecord(source.drive_state);
  if (!driveState) return null;

  const frustrationRecord = asNumberRecord(source.frustration) ?? {};
  const totalFrustration = asNumber(source.total_frustration) ?? asNumber(source.frustration);

  return {
    drive_state: driveState,
    drive_baseline: asNumberRecord(source.drive_baseline),
    frustration: frustrationRecord,
    temperature: asNumber(source.temperature) ?? 0,
    total_frustration: totalFrustration,
    proactive_fired: typeof source.proactive_fired === "boolean" ? source.proactive_fired : undefined,
    proactive_reply: typeof source.proactive_reply === "string" ? source.proactive_reply : undefined,
  };
}

export function mergeInjectedMemoryKeys(current: string[], text: string): string[] {
  const next = new Set(current);
  MEMORY_KEYWORDS.forEach((keyword) => {
    if (text.includes(keyword)) next.add(keyword);
  });
  return Array.from(next);
}

export function mergeDemoSnapshotIntoDebugState(current: EngineDebugState | null, snapshot: DemoSnapshot): EngineDebugState {
  return {
    ...(current || {}),
    drive_state: snapshot.drive_state,
    drive_baseline: snapshot.drive_baseline ?? current?.drive_baseline,
    frustration: Object.keys(snapshot.frustration).length ? snapshot.frustration : current?.frustration,
    total_frustration: snapshot.total_frustration ?? current?.total_frustration,
    temperature: snapshot.temperature,
  };
}

export function mergeEngineDebugState(current: EngineDebugState | null, next: EngineDebugState): EngineDebugState {
  const merged: EngineDebugState = {
    ...(current || {}),
    ...next,
  };

  if (!next.monologue && current?.monologue) {
    merged.monologue = current.monologue;
  }
  if ((!next.style_recall || next.style_recall.length === 0) && current?.style_recall?.length) {
    merged.style_recall = current.style_recall;
  }

  return merged;
}
