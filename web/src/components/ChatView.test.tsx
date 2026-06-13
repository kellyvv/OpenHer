import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { ChatView } from "./ChatView";

describe("ChatView errors", () => {
  test("shows backend errors inside the conversation", () => {
    const html = renderToStaticMarkup(
      <ChatView
        baseUrl="http://localhost:8000"
        persona={null}
        messages={[]}
        isConnected
        isTyping={false}
        error="LLM authentication failed"
        status={null}
        debugMode={false}
        onOpenEnginePanel={() => undefined}
        onOpenDemoBar={() => undefined}
        onOpenShowcase={() => undefined}
        onSend={() => undefined}
        onTyping={() => undefined}
        onBack={() => undefined}
        onOpenSettings={() => undefined}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("LLM authentication failed");
  });
});
