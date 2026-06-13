import { describe, expect, test } from "vitest";
import { toHistoryMessages } from "./messages";

describe("toHistoryMessages", () => {
  test("restores persisted assistant audio URLs", () => {
    const messages = toHistoryMessages([
      {
        id: 7,
        role: "assistant",
        content: "你好",
        modality: "语音",
        audio_url: "/api/voice/iris/hello.wav",
        created_at: 1,
      },
    ]);

    expect(messages[0]).toMatchObject({
      id: "h_7",
      role: "assistant",
      audioUrl: "/api/voice/iris/hello.wav",
      timestamp: 1000,
    });
  });
});
