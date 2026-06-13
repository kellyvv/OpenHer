import type { HistoryResponse, Persona, PersonasResponse, StatusResponse } from "../types/openher";

const DEFAULT_BASE_URL = import.meta.env.VITE_OPENHER_BASE_URL || "http://localhost:8000";

export function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "") || DEFAULT_BASE_URL;
}

export function defaultBaseUrl(): string {
  return normalizeBaseUrl(localStorage.getItem("openher.serverUrl") || DEFAULT_BASE_URL);
}

export function saveBaseUrl(baseUrl: string): string {
  const normalized = normalizeBaseUrl(baseUrl);
  localStorage.setItem("openher.serverUrl", normalized);
  return normalized;
}

export function getClientId(): string {
  const key = "openher.clientId";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const value = crypto.randomUUID();
  localStorage.setItem(key, value);
  return value;
}

export function mediaUrl(baseUrl: string, personaId: string, mediaType: string): string {
  return `${normalizeBaseUrl(baseUrl)}/api/persona/${encodeURIComponent(personaId)}/media/${mediaType}`;
}

export function selfieUrl(baseUrl: string, path?: string | null): string | null {
  return persistedMediaUrl(baseUrl, path);
}

export function persistedMediaUrl(baseUrl: string, path?: string | null): string | null {
  if (!path) return null;
  if (/^(?:https?:|blob:)/.test(path)) return path;
  return `${normalizeBaseUrl(baseUrl)}${path.startsWith("/") ? path : `/${path}`}`;
}

async function requestJson<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${normalizeBaseUrl(baseUrl)}${path}`, init);
  if (!res.ok) {
    throw new Error(`OpenHer API ${res.status}: ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export async function fetchStatus(baseUrl: string): Promise<StatusResponse> {
  return requestJson<StatusResponse>(baseUrl, "/api/status");
}

export async function fetchPersonas(baseUrl: string): Promise<Persona[]> {
  const data = await requestJson<PersonasResponse>(baseUrl, "/api/personas");
  return data.personas;
}

export async function fetchHistory(baseUrl: string, personaId: string, clientId: string): Promise<HistoryResponse> {
  const query = new URLSearchParams({ client_id: clientId, limit: "80" });
  return requestJson<HistoryResponse>(baseUrl, `/api/chat/history/${encodeURIComponent(personaId)}?${query}`);
}
