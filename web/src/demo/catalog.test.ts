import { describe, expect, test } from "vitest";
import {
  buildDemoMemoryPayload,
  buildDemoScenarioPayload,
  buildDemoTimeJumpPayload,
  DEMO_MEMORIES,
  DEMO_PERSONAS,
  DEMO_SCENARIOS,
  DEMO_TEST_ACTIONS,
  DEMO_TIME_JUMPS,
} from "./catalog";

describe("demo catalog", () => {
  test("includes the client demo scenarios and stress controls", () => {
    expect(DEMO_PERSONAS).toEqual([
      { id: "luna", name: "陆暖", mbti: "ENFP" },
      { id: "vivian", name: "顾霆微", mbti: "INTJ" },
      { id: "iris", name: "苏漫", mbti: "INFP" },
    ]);
    expect(DEMO_TIME_JUMPS.map((jump) => jump.hours)).toEqual([1, 4, 8, 24]);
    expect(DEMO_SCENARIOS.map((scenario) => scenario.id)).toEqual([
      "about_to_snap",
      "lonely",
      "deeply_bonded",
      "calm_reset",
    ]);
    expect(DEMO_TEST_ACTIONS.map((action) => action.id)).toContain("pressure_test");
    expect(DEMO_TEST_ACTIONS.map((action) => action.id)).toContain("neglect_stimulus");
  });

  test("builds websocket payloads compatible with the backend demo protocol", () => {
    expect(buildDemoTimeJumpPayload(8)).toEqual({ type: "demo_time_jump", hours: 8 });
    expect(buildDemoScenarioPayload("about_to_snap")).toEqual({ type: "demo_scenario", scenario_id: "about_to_snap" });
    expect(buildDemoMemoryPayload(DEMO_MEMORIES[0], "luna", "client-1")).toEqual({
      type: "demo_inject_memory",
      content: DEMO_MEMORIES[0].content,
      category: "preference",
      persona_id: "luna",
      client_id: "client-1",
    });
  });
});
