import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { MessageList } from "./MessageList";
import type { ChatMessage } from "../types/openher";

const baseMessage: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "",
  modality: "文字",
  timestamp: new Date("2026-06-02T12:00:00Z").getTime(),
};

describe("MessageList media rendering", () => {
  test("renders generated images as an accessible zoomable control", () => {
    const html = renderToStaticMarkup(
      <MessageList
        baseUrl="http://localhost:8000"
        messages={[
          {
            ...baseMessage,
            imageUrl: "/api/selfie/luna/photo.png",
          },
        ]}
      />,
    );

    expect(html).toContain('aria-label="查看生成图片"');
    expect(html).toContain('src="http://localhost:8000/api/selfie/luna/photo.png"');
  });

  test("renders voice replies with an accessible audio player", () => {
    const html = renderToStaticMarkup(
      <MessageList
        baseUrl="http://localhost:8000"
        messages={[
          {
            ...baseMessage,
            modality: "语音",
            audioUrl: "blob:http://localhost:5173/audio-1",
          },
        ]}
      />,
    );

    expect(html).toContain('aria-label="播放语音消息"');
    expect(html).toContain('class="voice-player"');
  });

  test("renders persisted voice replies from the backend", () => {
    const html = renderToStaticMarkup(
      <MessageList
        baseUrl="http://localhost:8000"
        messages={[
          {
            ...baseMessage,
            modality: "语音",
            audioUrl: "/api/voice/iris/voice.wav",
          },
        ]}
      />,
    );

    expect(html).toContain('src="http://localhost:8000/api/voice/iris/voice.wav"');
  });
});
