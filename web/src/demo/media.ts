import type { AppPhase } from "../types/openher";

export type DemoMediaType = "image" | "voice";

export function buildDemoMediaPayload(mediaType: DemoMediaType, personaId: string) {
  return {
    type: "demo_media_test",
    media_type: mediaType,
    persona_id: personaId,
  };
}

export function resolveDemoPersonaId(selectedPersonaId: string | null, phase: AppPhase): string {
  if (phase === "conversation" && selectedPersonaId) return selectedPersonaId;
  return "iris";
}
