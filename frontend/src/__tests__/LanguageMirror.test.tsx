import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AssistantChat } from "../components/assistant/AssistantChat";
import type { AssistantAskResponse } from "../lib/api";

/**
 * Language mirroring in the assistant chat:
 *  - there is no reply-language selector: the backend detects the query
 *    language itself (English / Roman Urdu / Urdu script) and answers in it;
 *  - the ask calls never pin a response_language override;
 *  - Urdu answers render RTL with a chip, English LTR;
 *  - a missing/unknown answer_language degrades to LTR without crashing.
 *
 * ../lib/api is mocked the way the existing tests do (importActual spread).
 */
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      assistantAsk: vi.fn(),
      assistantAskStream: vi.fn(),
      personalization: {
        getProfile: vi.fn(),
        getRecommendations: vi.fn(),
        dismissRecommendation: vi.fn(),
        sendFeedback: vi.fn(),
        deleteMyData: vi.fn(),
        setPersonalization: vi.fn(),
      },
    },
  };
});

function answer(overrides: Partial<AssistantAskResponse> = {}): AssistantAskResponse {
  return {
    question: "What is the penalty for late filing?",
    answer: "The penalty for late filing is 0.5% per month.",
    tools_used: [],
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
    },
    grounded: true,
    mode: "tools+rag",
    ...overrides,
  };
}

function renderChat(ask: unknown, askStream?: unknown) {
  return render(
    <MemoryRouter>
      <AssistantChat
        variant="personal"
        ask={ask as never}
        askStream={askStream as never}
        inputLabel="Ask a question"
        inputPlaceholder="e.g. penalty for late filing?"
        emptyDescription="No questions yet."
      />
    </MemoryRouter>,
  );
}

async function sendQuestion(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByTestId("assistant-input"), text);
  await user.click(screen.getByTestId("assistant-submit"));
  return user;
}

describe("Language mirroring", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    window.localStorage.clear();
    const { api } = await import("../lib/api");
    vi.mocked(api.personalization.getRecommendations).mockResolvedValue([]);
    vi.mocked(api.personalization.sendFeedback).mockResolvedValue({ recorded: true });
  });

  it("renders no reply-language selector — the backend auto-detects", () => {
    renderChat(vi.fn());
    expect(screen.queryByTestId("assistant-reply-language")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("fbr.assistant.reply_language")).toBeNull();
  });

  it("never pins a response_language override on the ask call", async () => {
    const ask = vi.fn().mockResolvedValue(answer({ answer_language: "roman_ur" }));
    renderChat(ask);

    await sendQuestion("mujhe kitna tax dena hai?");

    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(1);
    });
    // (query, file) only — no third "response_language" argument, so the
    // server resolves the language from the query itself.
    expect(ask.mock.calls[0]).toHaveLength(2);
    expect(ask.mock.calls[0][0]).toContain("kitna tax");
  });

  it("renders an Urdu answer right-to-left with no language chip", async () => {
    const ask = vi.fn().mockResolvedValue(answer({ answer_language: "ur" }));
    renderChat(ask);

    await sendQuestion("jurmana?");

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    // The chip is deliberately gone (clean ChatGPT-style bubbles); the RTL
    // direction is the only language affordance left on the bubble.
    expect(screen.queryByTestId("chat-lang-chip")).not.toBeInTheDocument();
    const bubble = screen.getByTestId("chat-answer").closest(".chat__bubble");
    expect(bubble).toHaveAttribute("dir", "rtl");
    expect(bubble).toHaveClass("chat__bubble--rtl");
  });

  it("renders an English answer left-to-right with no chip", async () => {
    const ask = vi.fn().mockResolvedValue(answer({ answer_language: "en" }));
    renderChat(ask);

    await sendQuestion("penalty?");

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-lang-chip")).not.toBeInTheDocument();
    const bubble = screen.getByTestId("chat-answer").closest(".chat__bubble");
    expect(bubble).toHaveAttribute("dir", "ltr");
    expect(bubble).not.toHaveClass("chat__bubble--rtl");
  });

  it("degrades to ltr without a chip when answer_language is missing", async () => {
    const ask = vi.fn().mockResolvedValue(answer());
    renderChat(ask);

    await sendQuestion("penalty?");

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-lang-chip")).not.toBeInTheDocument();
    const bubble = screen.getByTestId("chat-answer").closest(".chat__bubble");
    expect(bubble).toHaveAttribute("dir", "ltr");
  });

  it("degrades to ltr without crashing on an unknown answer_language", async () => {
    const ask = vi.fn().mockResolvedValue(answer({ answer_language: "fr" as never }));
    renderChat(ask);

    await sendQuestion("penalty?");

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-lang-chip")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-error")).not.toBeInTheDocument();
    const bubble = screen.getByTestId("chat-answer").closest(".chat__bubble");
    expect(bubble).toHaveAttribute("dir", "ltr");
  });
});
