import { persistedMediaUrl, selfieUrl } from "../api/openherClient";
import type { ChatMessage } from "../types/openher";
import { useState } from "react";

interface MessageListProps {
  baseUrl: string;
  messages: ChatMessage[];
}

function timeLabel(timestamp: number): string {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(timestamp));
}

export function MessageList({ baseUrl, messages }: MessageListProps) {
  const [zoomedImage, setZoomedImage] = useState<string | null>(null);

  return (
    <>
      <div className="message-list">
        {messages.map((message) => {
          const isUser = message.role === "user";
          const image = selfieUrl(baseUrl, message.imageUrl);
          const audio = persistedMediaUrl(baseUrl, message.audioUrl);
          return (
            <article className={`message-row ${isUser ? "message-user" : "message-assistant"}`} key={message.id}>
              <div className="message-content">
                {message.proactive && <span className="proactive-mark">主动消息</span>}
                {image && (
                  <button className="message-image-button" type="button" onClick={() => setZoomedImage(image)} aria-label="查看生成图片">
                    <img className="message-image" src={image} alt="OpenHer 生成图片" />
                  </button>
                )}
                {audio && (
                  <audio className="voice-player" controls src={audio} aria-label="播放语音消息">
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
      {zoomedImage && (
        <button className="image-lightbox" type="button" onClick={() => setZoomedImage(null)} aria-label="关闭图片预览">
          <img src={zoomedImage} alt="OpenHer 生成图片预览" />
        </button>
      )}
    </>
  );
}
