import { describe, expect, test } from "vitest";
import { persistedMediaUrl } from "./openherClient";

describe("persistedMediaUrl", () => {
  test("resolves backend-relative media URLs", () => {
    expect(persistedMediaUrl("http://localhost:8000", "/api/voice/iris/hello.wav")).toBe(
      "http://localhost:8000/api/voice/iris/hello.wav",
    );
  });

  test("keeps absolute and blob URLs unchanged", () => {
    expect(persistedMediaUrl("http://localhost:8000", "https://cdn.example/hello.wav")).toBe(
      "https://cdn.example/hello.wav",
    );
    expect(persistedMediaUrl("http://localhost:8000", "blob:http://localhost:5173/audio")).toBe(
      "blob:http://localhost:5173/audio",
    );
  });
});
