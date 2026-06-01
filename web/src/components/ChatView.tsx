import { useEffect, useRef, useState } from "react";
import { mediaUrl } from "../api/openherClient";
import { buildChatShellClassName } from "../layout/workspace";
import type { ChatMessage, EngineStatus, Persona } from "../types/openher";
import { EngineStatusPanel } from "./EngineStatusPanel";
import { MessageList } from "./MessageList";

interface ChatViewProps {
  baseUrl: string;
  persona: Persona | null;
  messages: ChatMessage[];
  isConnected: boolean;
  isTyping: boolean;
  status: EngineStatus | null;
  debugMode: boolean;
  onOpenEnginePanel: () => void;
  onOpenDemoBar: () => void;
  onOpenShowcase: () => void;
  onSend: (content: string) => void;
  onTyping: (active: boolean) => void;
  onBack: () => void;
  onOpenSettings: () => void;
}

export function ChatView({
  baseUrl,
  persona,
  messages,
  isConnected,
  isTyping,
  status,
  debugMode,
  onOpenEnginePanel,
  onOpenDemoBar,
  onOpenShowcase,
  onSend,
  onTyping,
  onBack,
  onOpenSettings,
}: ChatViewProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, isTyping]);

  const submit = () => {
    const content = input.trim();
    if (!content) return;
    setInput("");
    onSend(content);
  };

  return (
    <section className={buildChatShellClassName()} aria-label="OpenHer 对话">
      <header className="chat-header">
        <button className="icon-button" type="button" onClick={onBack} aria-label="返回角色列表">
          ‹
        </button>
        <button className="avatar-button" type="button" aria-label="角色头像">
          {persona && <img src={mediaUrl(baseUrl, persona.persona_id, "face")} alt={persona.name_zh || persona.name} />}
        </button>
        <div>
          <h1>{persona?.name_zh || persona?.name || "OpenHer"}</h1>
          <p>{isConnected ? "频率已连接" : "正在调频"}</p>
        </div>
        <div className="chat-tools">
          <button className="tool-button" type="button" onClick={onOpenEnginePanel} aria-label="打开人格引擎">
            引擎
          </button>
          <button className="tool-button" type="button" onClick={onOpenDemoBar} aria-label="打开演示控制条">
            演示
          </button>
          <button className="tool-button" type="button" onClick={onOpenShowcase} aria-label="打开情绪压力展示">
            情绪
          </button>
          <button className="icon-button settings-inline" type="button" onClick={onOpenSettings} aria-label="打开设置">
            ⚙
          </button>
        </div>
      </header>

      <div className="conversation-layout">
        <EngineStatusPanel status={status} debugMode={debugMode} />
        <div className="messages-column">
          <MessageList baseUrl={baseUrl} messages={messages} />
          {isTyping && <div className="typing-line">正在输入...</div>}
          <div ref={bottomRef} />
        </div>
      </div>

      <form
        className="input-line"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <input
          value={input}
          placeholder="写点什么..."
          onChange={(event) => setInput(event.target.value)}
          onFocus={() => onTyping(true)}
          onBlur={() => onTyping(false)}
          aria-label="输入消息"
        />
        <button className="send-button" type="submit" aria-label="发送消息">
          ↑
        </button>
      </form>
    </section>
  );
}
