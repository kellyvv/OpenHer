import { describe, expect, test } from "vitest";
import {
  extractDemoSnapshot,
  extractEngineDebugState,
  mergeDemoSnapshotIntoDebugState,
  mergeEngineDebugState,
  mergeInjectedMemoryKeys,
} from "./state";

describe("demo state helpers", () => {
  test("extracts debug state from chat_end payload and enriches turn metadata", () => {
    const state = extractEngineDebugState({
      type: "chat_end",
      turn_count: 7,
      last_reward: 0.42,
      relationship: { depth: 0.6 },
      debug: {
        signals: { warmth: 0.8 },
        drive_state: { connection: 0.3 },
        frustration: { connection: 1.4 },
        total_frustration: 1.4,
        temperature: 0.22,
        monologue: "我有点在意这件事。",
      },
    });

    expect(state?.turn_count).toBe(7);
    expect(state?.reward).toBe(0.42);
    expect(state?.relationship?.depth).toBe(0.6);
    expect(state?.signals?.warmth).toBe(0.8);
    expect(state?.total_frustration).toBe(1.4);
  });

  test("builds demo snapshot from either demo_state or debug payload", () => {
    const snapshot = extractDemoSnapshot({
      drive_state: { connection: 0.1 },
      drive_baseline: { connection: 0.5 },
      frustration: { connection: 2.4 },
      temperature: 0.31,
      total_frustration: 2.4,
    });

    expect(snapshot?.drive_state.connection).toBe(0.1);
    expect(snapshot?.frustration.connection).toBe(2.4);
    expect(snapshot?.temperature).toBe(0.31);
  });

  test("tracks injected memory keywords once", () => {
    expect(mergeInjectedMemoryKeys(["团子"], "用户喜欢喝美式咖啡，不加糖")).toEqual(["团子", "美式"]);
  });

  test("merges demo_state values into the debug panel state", () => {
    const state = mergeDemoSnapshotIntoDebugState(null, {
      drive_state: { connection: 0.2 },
      drive_baseline: { connection: 0.5 },
      frustration: { connection: 1.7 },
      temperature: 0.28,
      total_frustration: 1.7,
    });

    expect(state.drive_state?.connection).toBe(0.2);
    expect(state.drive_baseline?.connection).toBe(0.5);
    expect(state.frustration).toEqual({ connection: 1.7 });
    expect(state.total_frustration).toBe(1.7);
    expect(state.temperature).toBe(0.28);
  });

  test("does not replace a useful monologue with an empty debug payload", () => {
    const state = mergeEngineDebugState(
      { monologue: "上一轮有独白", style_recall: [{ text: "片段", distance: 0.3 }] },
      { monologue: "", signals: { warmth: 0.5 }, style_recall: [] },
    );

    expect(state.monologue).toBe("上一轮有独白");
    expect(state.style_recall).toEqual([{ text: "片段", distance: 0.3 }]);
    expect(state.signals?.warmth).toBe(0.5);
  });
});
