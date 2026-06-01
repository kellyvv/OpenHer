import { selfieUrl } from "../api/openherClient";
import type { ChatMessage } from "../types/openher";

interface MessageListProps {
  baseUrl: string;
  messages: ChatMessage[];
}

function timeLabel(timestamp: number): string {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(timestamp));
}

export function MessageList({ baseUrl, messages }: MessageListProps) {
  return (
    <div className="message-list">
      {messages.map((message) => {
        const isUser = message.role === "user";
        const image = selfieUrl(baseUrl, message.imageUrl);
        return (
          <article className={`message-row ${isUser ? "message-user" : "message-assistant"}`} key={message.id}>
            <div className="message-content">
              {message.proactive && <span className="proactive-mark">主动消息</span>}
              {image && <img className="message-image" src={image} alt="OpenHer 生成图片" />}
              {message.audioUrl && (
                <audio className="voice-player" controls src={message.audioUrl}>
                  <track kind="captions" />
                </audio>
              )}
              {message.content && <p className={message.modality === "表情" ? "emoji-message" : ""}>{message.content}</p>}
              <time>{timeLabel(message.timestamp)}</time>
            </div>
          </article>
        );
      })}
    </div>
  );
}
