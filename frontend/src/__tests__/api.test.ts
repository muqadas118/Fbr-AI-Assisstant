import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, getApiConfig, ApiError, NetworkError } from "../lib/api";

describe("API Client", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    globalThis.fetch = vi.fn() as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  describe("getApiConfig", () => {
    it("returns default config when env vars not set", () => {
      const config = getApiConfig();
      expect(config.baseUrl).toBe("http://127.0.0.1:8000");
      expect(config.timeoutMs).toBe(30000);
    });

    it("reads base URL from env var", () => {
      vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com");
      const config = getApiConfig();
      expect(config.baseUrl).toBe("https://api.example.com");
    });

    it("reads timeout from env var", () => {
      vi.stubEnv("VITE_API_TIMEOUT_MS", "10000");
      const config = getApiConfig();
      expect(config.timeoutMs).toBe(10000);
    });

    it("strips trailing slash from base URL", () => {
      vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com/");
      const config = getApiConfig();
      expect(config.baseUrl).toBe("https://api.example.com");
    });
  });

  describe("api.health", () => {
    it("calls /health endpoint", async () => {
      const mockResponse = { status: "ok", version: "1.0.0" };
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(mockResponse)),
      });

      const result = await api.health();
      expect(result).toEqual(mockResponse);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/health",
        expect.objectContaining({
          method: "GET",
        }),
      );
    });

    it("throws ApiError on non-ok response", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve(JSON.stringify({ detail: "Server error" })),
      });

      await expect(api.health()).rejects.toThrow(ApiError);
    });

    it("throws NetworkError on timeout", async () => {
      vi.stubEnv("VITE_API_TIMEOUT_MS", "1");
      globalThis.fetch = vi.fn(
        (_url: unknown, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            });
          }),
      ) as unknown as typeof fetch;

      await expect(api.health()).rejects.toThrow(NetworkError);
    });
  });

  describe("api.answer", () => {
    const mockAnswer = {
      question: "Test query",
      domains: ["tax"],
      primary_domain: "tax",
      multi_domain: false,
      routing: {},
      domain_results: [],
      answer: "Test answer",
      sources: [],
      verification: {
        passed: true,
        checks: {
          answer_size: { passed: true, reason: "ok" },
          section_consistency: { passed: true, reason: "ok" },
          grounding: { passed: true, reason: "ok" },
          speculation: { passed: true, reason: "ok" },
        },
        failed_checks: [],
        reason: "ok",
        grounded: true,
      },
    };

    it("posts to /answer endpoint with query", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(mockAnswer)),
      });

      const result = await api.answer("Test query");
      expect(result).toEqual(mockAnswer);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/answer",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ query: "Test query" }),
        }),
      );
    });

    it("throws ApiError on 400 with proper detail", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: () => Promise.resolve(JSON.stringify({ detail: "Invalid query" })),
      });

      try {
        await api.answer("bad");
        expect.fail("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(400);
        expect((err as ApiError).detail).toBe("Invalid query");
      }
    });

    it("throws ApiError on 422 with proper detail", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        text: () => Promise.resolve(JSON.stringify({ detail: "Validation error" })),
      });

      try {
        await api.answer("");
        expect.fail("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(422);
      }
    });

    it("throws ApiError on 503 with proper detail", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: () => Promise.resolve(JSON.stringify({ detail: "Service unavailable" })),
      });

      try {
        await api.answer("query");
        expect.fail("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(503);
      }
    });

    it("handles non-JSON error responses", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve("Internal Server Error"),
      });

      try {
        await api.answer("query");
        expect.fail("should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).detail).toBe("Internal Server Error");
      }
    });

    it("throws NetworkError on network failure", async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network error"));
      await expect(api.answer("query")).rejects.toThrow(NetworkError);
    });
  });

  describe("Error classes", () => {
    it("ApiError has correct properties", () => {
      const err = new ApiError("Test error", 400, "Bad request");
      expect(err.name).toBe("ApiError");
      expect(err.message).toBe("Test error");
      expect(err.status).toBe(400);
      expect(err.detail).toBe("Bad request");
    });

    it("NetworkError has correct properties", () => {
      const err = new NetworkError("Connection failed");
      expect(err.name).toBe("NetworkError");
      expect(err.message).toBe("Connection failed");
    });
  });
});
