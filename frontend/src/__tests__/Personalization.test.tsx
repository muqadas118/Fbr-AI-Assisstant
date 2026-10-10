import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AssistantPage } from "../pages/personal/AssistantPage";
import { PersonalizationPanel } from "../components/assistant/PersonalizationPanel";
import { RecommendationStrip } from "../components/assistant/RecommendationStrip";
import type { PersonalizationProfile, Recommendation } from "../lib/api";
import { api } from "../lib/api";
import { useNotification } from "../state/notifications";

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

const mockRecommendations: Recommendation[] = [
  {
    id: "rec-1",
    kind: "deadline",
    title: "File your income tax return",
    body: "Your return for tax year 2026 is due soon.",
    action_label: "Open calendar",
    action_path: "/personal/calendar",
    priority: 90,
    source: "profile",
  },
  {
    id: "rec-2",
    kind: "document",
    title: "Upload your salary certificate",
    body: "Withholding statements speed up your filing.",
    action_label: "Open documents",
    action_path: "/personal/documents",
    priority: 60,
    source: "profile",
  },
];

const mockProfile: PersonalizationProfile = {
  user_id: "u-1",
  enabled: true,
  signals: { entity_type: "individual", tax_year: 2026 },
  top_domains: [
    ["income_tax", 0.82],
    ["sales_tax", 0.41],
  ],
  total_interactions: 12,
  last_active: "2026-10-01T10:00:00Z",
};

function askResponse(overrides: {
  personalization?: PersonalizationPanelish;
} = {}) {
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
  } as never;
}

type PersonalizationPanelish = {
  enabled: boolean;
  recommendations: Recommendation[];
  profile_summary: { top_domains: Array<[string, number]>; total_interactions: number } | null;
};

const enabledPersonalization: PersonalizationPanelish = {
  enabled: true,
  recommendations: mockRecommendations,
  profile_summary: { top_domains: [["income_tax", 0.82]], total_interactions: 12 },
};

async function setupMocks() {
  const { api } = await import("../lib/api");
  mockAsk(askResponse());
  vi.mocked(api.personalization.getProfile).mockResolvedValue(mockProfile);
  vi.mocked(api.personalization.getRecommendations).mockResolvedValue(mockRecommendations);
  vi.mocked(api.personalization.dismissRecommendation).mockResolvedValue({ dismissed: true });
  vi.mocked(api.personalization.sendFeedback).mockResolvedValue({ recorded: true });
  vi.mocked(api.personalization.deleteMyData).mockResolvedValue({ deleted: 7 });
  vi.mocked(api.personalization.setPersonalization).mockImplementation(
    async (enabled: boolean) => ({ enabled }),
  );
}

/** Both transports (plain + SSE) answer with the same payload. */
function mockAsk(resp: unknown) {
  vi.mocked(api.assistantAsk).mockResolvedValue(resp as never);
  vi.mocked(api.assistantAskStream).mockImplementation(async (query, handlers) => {
    handlers?.onMeta?.({ question: query, tools_used: [], sources: [] });
    return resp as never;
  });
}

describe("Personalization", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    useNotification.setState({ current: null });
    await setupMocks();
  });

  /* ---------------- panel ---------------- */

  it("renders the learned profile with top domains and stats", async () => {
    render(
      <MemoryRouter>
        <PersonalizationPanel open onClose={() => {}} testId="pers" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("pers-profile")).toBeInTheDocument();
    });
    expect(screen.getByTestId("pers-profile")).toHaveTextContent("12 interactions");
    expect(screen.getByTestId("pers-profile")).toHaveTextContent("Entity: individual");
    expect(screen.getByTestId("pers-profile")).toHaveTextContent("Tax year: 2026");
    expect(screen.getByTestId("pers-profile")).toHaveTextContent("income_tax");
    expect(screen.getByTestId("pers-state")).toHaveTextContent("On");
    expect(
      screen.getByText(
        /Learning is on-device-per-account: your questions shape your recommendations\. We never use your data to train shared models\./,
      ),
    ).toBeInTheDocument();
  });

  it("toggles personalization on and off via the endpoint", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PersonalizationPanel open onClose={() => {}} testId="pers" />
      </MemoryRouter>,
    );

    const toggle = await screen.findByTestId("pers-toggle");
    expect(toggle).toBeChecked();
    expect(screen.getByTestId("pers-state")).toHaveTextContent("On");

    await user.click(toggle);
    await waitFor(() => {
      expect(api.personalization.setPersonalization).toHaveBeenCalledWith(false);
    });
    await waitFor(() => {
      expect(screen.getByTestId("pers-state")).toHaveTextContent("Off");
    });

    await user.click(screen.getByTestId("pers-toggle"));
    await waitFor(() => {
      expect(api.personalization.setPersonalization).toHaveBeenCalledWith(true);
    });
    await waitFor(() => {
      expect(screen.getByTestId("pers-state")).toHaveTextContent("On");
    });
  });

  it("shows an error and keeps the toggle honest when the toggle call fails", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.personalization.setPersonalization).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PersonalizationPanel open onClose={() => {}} testId="pers" />
      </MemoryRouter>,
    );

    await user.click(await screen.findByTestId("pers-toggle"));
    await waitFor(() => {
      expect(useNotification.getState().current?.kind).toBe("err");
    });
    // Refetched profile — the switch stays on.
    await waitFor(() => {
      expect(api.personalization.getProfile).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId("pers-state")).toHaveTextContent("On");
  });

  it("delete my data asks for confirmation before calling the endpoint", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PersonalizationPanel open onClose={() => {}} testId="pers" />
      </MemoryRouter>,
    );

    await user.click(await screen.findByTestId("pers-delete"));
    expect(screen.getByTestId("pers-confirm")).toBeInTheDocument();
    expect(api.personalization.deleteMyData).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("pers-delete-cancel"));
    expect(screen.queryByTestId("pers-confirm")).not.toBeInTheDocument();
    expect(api.personalization.deleteMyData).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("pers-delete"));
    await user.click(screen.getByTestId("pers-delete-confirm"));
    await waitFor(() => {
      expect(api.personalization.deleteMyData).toHaveBeenCalledTimes(1);
    });
    // Profile refetched after the wipe.
    await waitFor(() => {
      expect(api.personalization.getProfile).toHaveBeenCalledTimes(2);
    });
    expect(useNotification.getState().current?.message).toContain("Deleted 7");
  });

  it("surfaces a loading state while the profile is in flight", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.personalization.getProfile).mockImplementation(() => new Promise(() => {}));

    render(
      <MemoryRouter>
        <PersonalizationPanel open onClose={() => {}} testId="pers" />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("pers-loading")).toBeInTheDocument();
  });

  /* ---------------- recommendation strip ---------------- */

  it("renders nothing when there are no recommendations", () => {
    render(
      <MemoryRouter>
        <RecommendationStrip recommendations={[]} testId="recs" />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("recs")).not.toBeInTheDocument();
  });

  it("dismisses a recommendation optimistically and calls the endpoint", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <RecommendationStrip recommendations={mockRecommendations} testId="recs" />
      </MemoryRouter>,
    );

    expect(screen.getAllByTestId("recs-item")).toHaveLength(2);

    await user.click(screen.getAllByTestId("recs-dismiss")[0]);
    await waitFor(() => {
      expect(api.personalization.dismissRecommendation).toHaveBeenCalledWith("rec-1");
    });
    await waitFor(() => {
      expect(screen.getAllByTestId("recs-item")).toHaveLength(1);
    });
    expect(screen.getByText("Upload your salary certificate")).toBeInTheDocument();
    expect(useNotification.getState().current?.kind).toBe("ok");
  });

  it("restores a recommendation when the dismiss call fails", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.personalization.dismissRecommendation).mockRejectedValue(new Error("nope"));
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <RecommendationStrip recommendations={mockRecommendations} testId="recs" />
      </MemoryRouter>,
    );

    await user.click(screen.getAllByTestId("recs-dismiss")[0]);
    await waitFor(() => {
      expect(useNotification.getState().current?.kind).toBe("err");
    });
    await waitFor(() => {
      expect(screen.getAllByTestId("recs-item")).toHaveLength(2);
    });
  });

  it("navigates to the recommendation action path", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <RecommendationStrip recommendations={mockRecommendations} testId="recs" />
      </MemoryRouter>,
    );

    await user.click(screen.getAllByTestId("recs-action")[0]);
    // Navigation happened inside MemoryRouter — no crash, no error toast.
    expect(useNotification.getState().current).toBeNull();
  });

  /* ---------------- chat wiring ---------------- */

  /**
   * The chat UI no longer surfaces personalization inline (no strip, no
   * 👍/👎 buttons, no "For you" header row) — it is kept deliberately clean,
   * ChatGPT-style. Learning still happens backend-side. The component-level
   * tests above cover the panel + strip in isolation.
   */

  function renderAssistant() {
    return render(
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>,
    );
  }

  it("renders no recommendation strip or feedback buttons in the chat", async () => {
    mockAsk(askResponse({ personalization: enabledPersonalization }));

    const user = userEvent.setup();
    renderAssistant();
    await user.type(screen.getByTestId("assistant-input"), "penalty?");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-recs")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-feedback-up")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-feedback-down")).not.toBeInTheDocument();
  });

  it("keeps the chat clean when personalization endpoints fail", async () => {
    mockAsk(askResponse());
    vi.mocked(api.personalization.getRecommendations).mockRejectedValue(new Error("offline"));

    const user = userEvent.setup();
    renderAssistant();
    await user.type(screen.getByTestId("assistant-input"), "penalty?");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-recs")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-error")).not.toBeInTheDocument();
  });

  it("renders no For-you header controls in the chat", () => {
    renderAssistant();
    expect(screen.queryByTestId("assistant-for-you")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-personalization")).not.toBeInTheDocument();
  });
});
