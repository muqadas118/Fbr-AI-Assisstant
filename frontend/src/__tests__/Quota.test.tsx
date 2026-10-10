import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AssistantPage } from "../pages/personal/AssistantPage";
import { ApiError, api, type QuotaSnapshot } from "../lib/api";
import { useNotification } from "../state/notifications";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      assistantAsk: vi.fn(),
      assistantAskStream: vi.fn(),
      // Mocked wholesale so a GET /quota never touches the network.
      quota: {
        get: vi.fn(),
      },
    },
  };
});

function quota(overrides: {
  enabled?: boolean;
  messages?: { used: number; limit: number; remaining: number };
  uploads?: { used: number; limit: number; remaining: number };
} = {}): QuotaSnapshot {
  return {
    enabled: overrides.enabled ?? true,
    user_id: "dev-user",
    date: "2026-10-10",
    timezone: "Asia/Karachi",
    reset_at: "2026-10-11T00:00:00+05:00",
    messages: overrides.messages ?? { used: 3, limit: 10, remaining: 7 },
    uploads: overrides.uploads ?? { used: 2, limit: 5, remaining: 3 },
  };
}

/** A settled + streamed answer; personalization off so no fallback fetch. */
function askResponse() {
  return {
    question: "penalty?",
    answer: "The penalty is 0.5% per month.",
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
    personalization: { enabled: false, recommendations: [], profile_summary: null },
  } as never;
}

function mockAsk(resp: unknown) {
  vi.mocked(api.assistantAsk).mockResolvedValue(resp as never);
  vi.mocked(api.assistantAskStream).mockImplementation(async (query, handlers) => {
    handlers?.onMeta?.({ question: query, tools_used: [], sources: [] });
    return resp as never;
  });
}

function renderAssistant() {
  return render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  );
}

describe("Daily quota UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNotification.setState({ current: null });
    mockAsk(askResponse());
    vi.mocked(api.quota.get).mockResolvedValue(quota());
  });

  it("shows a nudging nudge — and no header counter — when the budget runs low", async () => {
    vi.mocked(api.quota.get).mockResolvedValue(
      quota({ messages: { used: 8, limit: 10, remaining: 2 }, uploads: { used: 3, limit: 5, remaining: 2 } }),
    );
    renderAssistant();

    const hint = await screen.findByTestId("assistant-quota-hint");
    expect(hint).toHaveTextContent(/You have 2 messages left today/);
    expect(hint).toHaveTextContent(/resets at/i);
    // The permanent "N/M msgs · N/M files" header counter is gone for good.
    expect(screen.queryByTestId("assistant-quota")).not.toBeInTheDocument();
  });

  it("nudges about uploads when only one upload remains", async () => {
    vi.mocked(api.quota.get).mockResolvedValue(
      quota({ messages: { used: 1, limit: 10, remaining: 9 }, uploads: { used: 4, limit: 5, remaining: 1 } }),
    );
    renderAssistant();

    const hint = await screen.findByTestId("assistant-quota-hint");
    expect(hint).toHaveTextContent(/You have 1 upload left today/);
  });

  it("shows no nudge while the budget is comfortable", async () => {
    renderAssistant();
    await screen.findByTestId("assistant-input");
    await waitFor(() => expect(api.quota.get).toHaveBeenCalled());
    expect(screen.queryByTestId("assistant-quota-hint")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-quota")).not.toBeInTheDocument();
  });

  it("disables the send button and shows a banner when no messages remain", async () => {
    vi.mocked(api.quota.get).mockResolvedValue(
      quota({ messages: { used: 10, limit: 10, remaining: 0 } }),
    );
    const user = userEvent.setup();
    renderAssistant();

    await user.type(screen.getByTestId("assistant-input"), "penalty?");
    expect(screen.getByTestId("assistant-submit")).toBeDisabled();
    expect(screen.getByTestId("assistant-quota-banner")).toHaveTextContent(
      /daily message limit reached/i,
    );
    expect(screen.queryByTestId("assistant-quota-hint")).not.toBeInTheDocument();
  });

  it("disables the file-attach control when no uploads remain", async () => {
    vi.mocked(api.quota.get).mockResolvedValue(
      quota({ uploads: { used: 5, limit: 5, remaining: 0 } }),
    );
    renderAssistant();

    await waitFor(() => expect(api.quota.get).toHaveBeenCalled());
    expect(screen.getByTestId("assistant-attach")).toBeDisabled();
    expect(screen.getByTestId("assistant-quota-banner")).toHaveTextContent(
      /daily file upload limit reached/i,
    );
  });

  it("surfaces a 429 server detail via the toast and refreshes the quota", async () => {
    const detail = "Daily message limit reached — try again after 12:00 AM.";
    vi.mocked(api.assistantAskStream).mockRejectedValue(new ApiError("429", 429, detail));
    vi.mocked(api.assistantAsk).mockRejectedValue(new ApiError("429", 429, detail));

    const user = userEvent.setup();
    renderAssistant();
    await waitFor(() => expect(api.quota.get).toHaveBeenCalled());
    const callsAfterMount = vi.mocked(api.quota.get).mock.calls.length;

    await user.type(screen.getByTestId("assistant-input"), "penalty?");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(useNotification.getState().current?.message).toBe(detail);
    });
    await waitFor(() => {
      expect(vi.mocked(api.quota.get).mock.calls.length).toBeGreaterThan(callsAfterMount);
    });
  });

  it("hides the nudge and leaves the composer usable when quotas are disabled", async () => {
    vi.mocked(api.quota.get).mockResolvedValue(quota({ enabled: false }));
    const user = userEvent.setup();
    renderAssistant();

    await waitFor(() => {
      expect(api.quota.get).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("assistant-quota-hint")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-quota")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-quota-banner")).not.toBeInTheDocument();

    await user.type(screen.getByTestId("assistant-input"), "penalty?");
    expect(screen.getByTestId("assistant-submit")).not.toBeDisabled();
  });

  it("degrades silently and never blocks sending when GET /quota fails", async () => {
    vi.mocked(api.quota.get).mockRejectedValue(new Error("quota offline"));
    const user = userEvent.setup();
    renderAssistant();

    await waitFor(() => {
      expect(api.quota.get).toHaveBeenCalled();
    });
    expect(useNotification.getState().current).toBeNull();
    expect(screen.queryByTestId("assistant-quota-hint")).not.toBeInTheDocument();

    await user.type(screen.getByTestId("assistant-input"), "penalty?");
    const send = screen.getByTestId("assistant-submit");
    expect(send).not.toBeDisabled();

    await user.click(send);
    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-error")).not.toBeInTheDocument();
  });
});
