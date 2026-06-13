import type { ChatMessage, HistoryMessage } from "../types/openher";

export function toHistoryMessages(items: HistoryMessage[]): ChatMessage[] {
  return items.map((item) => ({
    id: `h_${item.id}`,
    role: item.role,
    content: item.content,
    modality: item.modality || "文字",
    imageUrl: item.role === "assistant" ? item.image_url : null,
    audioUrl: item.role === "assistant" ? item.audio_url : null,
    timestamp: item.created_at ? item.created_at * 1000 : Date.now(),
    sendStatus: "sent",
  }));
}
