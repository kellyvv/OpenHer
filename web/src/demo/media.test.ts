import { describe, expect, test } from "vitest";
import { buildDemoMediaPayload, resolveDemoPersonaId } from "./media";

describe("demo media helpers", () => {
  test("builds image and voice websocket commands", () => {
    expect(buildDemoMediaPayload("image", "luna")).toEqual({
      type: "demo_media_test",
      media_type: "image",
      persona_id: "luna",
    });
    expect(buildDemoMediaPayload("voice", "iris")).toEqual({
      type: "demo_media_test",
      media_type: "voice",
      persona_id: "iris",
    });
  });

  test("uses Iris when the demo is opened outside a conversation", () => {
    expect(resolveDemoPersonaId("luna", "conversation")).toBe("luna");
    expect(resolveDemoPersonaId("luna", "discovery")).toBe("iris");
    expect(resolveDemoPersonaId(null, "awakening")).toBe("iris");
  });
});
