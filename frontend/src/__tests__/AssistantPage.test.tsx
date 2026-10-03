import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { AssistantPage } from "../pages/personal/AssistantPage";
import { BusinessAssistantPage } from "../pages/business/BusinessAssistantPage";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      health: vi.fn(),
      answer: vi.fn(),
      assistantAsk: vi.fn(),
      // Streaming transport — mocked like assistantAsk; a per-test mock of
      // assistantAsk also drives the stream unless a test overrides it.
      assistantAskStream: vi.fn(),
    },
  };
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

const mockSource = {
  chunk_id: "chunk-1",
  document_id: "doc-1",
  source: "IncomeTaxOrdinance2001_upto2025.pdf",
  source_path: "data/raw/04-source-docs/IncomeTaxOrdinance2001_upto2025.pdf",
  source_sha256: "abc123",
  page: 42,
  page_start: 42,
  page_end: 43,
  section: "Section 182",
  section_reference: "182",
  section_number: "182",
  law_tag: "Income Tax Ordinance 2001",
  multi_law_candidate: false,
  score: 0.87,
  semantic_score: 0.8,
  bm25_score: 0.9,
  exact_match: true,
};

const mockAnswerResponse = {
  question: "What is the penalty for late filing?",
  domains: ["tax", "compliance"],
  primary_domain: "tax",
  multi_domain: false,
  routing: {},
  domain_results: [],
  answer: "The penalty for late filing is 0.5% per month.",
  sources: [mockSource],
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
};

describe("AssistantPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockResolvedValue(mockAnswerResponse as never);
    // Default stream mock: reuse the assistantAsk mock's behavior (resolve /
    // reject / hang) so per-test setups apply to both transports.
    vi.mocked(api.assistantAskStream).mockImplementation(async (query, handlers) => {
      handlers?.onMeta?.({
        question: query,
        tools_used: [],
        sources: [],
        verification: mockAnswerResponse.verification,
        grounded: true,
        mode: "tools+rag",
      });
      handlers?.onDelta?.(mockAnswerResponse.answer);
      return vi.mocked(api.assistantAsk)(query) as never;
    });
  });

  it("renders the assistant interface", () => {
    renderWithRouter(<AssistantPage />);
    expect(screen.getByText("AI Tax Assistant")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-input")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-form")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-empty")).toBeInTheDocument();
    expect(
      screen.getByText(
        "No questions yet. Ask anything about FBR tax, filing obligations, notice types, or compliance timelines — or attach a document and let the AI analyze it.",
      ),
    ).toBeInTheDocument();
  });

  it("displays the subtitle explaining the verified pipeline", () => {
    renderWithRouter(<AssistantPage />);
    expect(screen.getByText(/grounds every answer in official FBR law/)).toBeInTheDocument();
  });

  it("submits a query and displays the response", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "What is the penalty for late filing?");

    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
    });
    expect(screen.getByText("The penalty for late filing is 0.5% per month.")).toBeInTheDocument();
    // Smart assistant endpoint is used, not the plain /answer one.
    const { api } = await import("../lib/api");
    expect(vi.mocked(api.assistantAsk)).toHaveBeenCalled();
  });

  it("streams the answer token-by-token before settling on the final payload", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.assistantAskStream).mockImplementation(async (_query, handlers) => {
      handlers?.onMeta?.({ grounded: true, mode: "rag", tools_used: [], sources: [] });
      handlers?.onDelta?.("The penalty for late");
      handlers?.onDelta?.(" filing is 0.5% per month.");
      return mockAnswerResponse as never;
    });

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.type(screen.getByTestId("assistant-input"), "Test query");
    await user.click(screen.getByTestId("assistant-submit"));

    // Deltas render live into the bubble (no placeholder-only flash).
    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toHaveTextContent("The penalty for late");
    });
    await waitFor(() => {
      expect(screen.getByTestId("chat-answer")).toHaveTextContent("0.5% per month.");
    });
    // Stream completed -> final payload (sources + verification) is attached.
    await waitFor(() => {
      expect(screen.getByTestId("chat-source-chips")).toBeInTheDocument();
    });
    expect(vi.mocked(api.assistantAsk)).not.toHaveBeenCalled();
  });

  it("reveals the answer with a typewriter caret (animation-capable envs)", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.type(screen.getByTestId("assistant-input"), "Test query");
    await user.click(screen.getByTestId("assistant-submit"));

    // While revealing (or once complete), the answer carries the caret marker
    // class only when the environment can animate; jsdom cannot, so the full
    // text renders immediately and the caret is absent.
    await waitFor(() => {
      expect(screen.getByTestId("chat-assistant")).toBeInTheDocument();
    });
    const answer = screen.getByTestId("chat-answer");
    expect(answer).toHaveTextContent("The penalty for late filing is 0.5% per month.");
    expect(answer.querySelector(".chat__caret")).toBeNull();
  });

  it("shows loading state during API call", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");

    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    expect(screen.getByTestId("assistant-thinking")).toBeInTheDocument();
  });

  it("shows honest error state when API fails", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockRejectedValue(new Error("Network failure"));

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");

    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("chat-error")).toBeInTheDocument();
    });
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText(/unexpected error occurred/i)).toBeInTheDocument();
  });

  it("shows a friendly error on unauthorized failures (no login CTA — login is backend-wired)", async () => {
    const { api, ApiError, isUnauthorized } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockRejectedValue(
      new ApiError("Unauthorized", 401, "token missing"),
    );
    expect(isUnauthorized(new ApiError("Unauthorized", 401, "x"))).toBe(true);

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.type(screen.getByTestId("assistant-input"), "Test query");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-error")).toBeInTheDocument();
    });
    // Login banner/CTA removed from the assistant tab.
    expect(screen.queryByText("Login required")).not.toBeInTheDocument();
    expect(screen.queryByTestId("message-login")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assistant-login-banner")).not.toBeInTheDocument();
  });

  it("shows source chips and toggles the full citation list", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.type(screen.getByTestId("assistant-input"), "Test query");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-source-chips")).toBeInTheDocument();
    });
    expect(screen.getByTestId("chat-source-chips")).toHaveTextContent(
      "IncomeTaxOrdinance2001 upto2025",
    );
    expect(screen.getByTestId("chat-source-chips")).toHaveTextContent("p. 42");

    expect(screen.queryByTestId("chat-sources")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("chat-sources-toggle"));
    expect(screen.getByTestId("chat-sources")).toBeInTheDocument();
  });

  it("copies the answer with copied-state feedback", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.type(screen.getByTestId("assistant-input"), "Test query");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-copy")).toBeInTheDocument();
    });

    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    await user.click(screen.getByTestId("chat-copy"));
    await waitFor(() => {
      expect(screen.getByTestId("chat-copy")).toHaveTextContent("Copied");
    });
    expect(writeText).toHaveBeenCalledWith("The penalty for late filing is 0.5% per month.");
  });

  it("answers greetings locally without the verification panel", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.type(screen.getByTestId("assistant-input"), "hi");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getAllByTestId("chat-answer")[0]).toHaveTextContent("Hello!");
    });
    expect(api.assistantAsk).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-verification")).not.toBeInTheDocument();
    expect(screen.queryByText(/NOT VERIFIED/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-error")).not.toBeInTheDocument();
  });

  it("turns the API's too-short rejection into a friendly hint, not an error", async () => {
    const { api, ApiError } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockRejectedValue(
      new ApiError("Bad Request", 400, "Question is too short (min 3 characters)."),
    );

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    // "zz" is not a greeting, so it reaches the API which rejects it as too short.
    await user.type(screen.getByTestId("assistant-input"), "zz");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByText(/slightly longer question/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chat-error")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-verification")).not.toBeInTheDocument();
  });

  it("attaches a text file and shows it in the composer and the sent message", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const file = new File(["NTN 1234567 filing history"], "notes.txt", { type: "text/plain" });
    fireEvent.change(screen.getByTestId("assistant-file-input"), {
      target: { files: [file] },
    });

    await waitFor(() => {
      expect(screen.getByTestId("assistant-file-chip")).toBeInTheDocument();
    });
    expect(screen.getByTestId("assistant-file-chip")).toHaveTextContent("notes.txt");

    await user.type(screen.getByTestId("assistant-input"), "Summarize this");
    await user.click(screen.getByTestId("assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-user")).toHaveTextContent("Summarize this");
    });
    expect(screen.getByTestId("chat-user")).toHaveTextContent("notes.txt");
    expect(screen.getByTestId("chat-answer")).toBeInTheDocument();
  });

  it("shows a graceful notice when voice input is unsupported", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    await user.click(screen.getByTestId("assistant-mic"));

    expect(screen.getByTestId("assistant-notice")).toHaveTextContent(
      /voice input isn't supported/i,
    );
  });

  it("shows clear conversation button after messages", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    expect(screen.queryByTestId("assistant-clear")).not.toBeInTheDocument();

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");
    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("assistant-clear")).toBeInTheDocument();
    });
  });

  it("clears conversation when clear button is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");
    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("assistant-clear")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("assistant-clear"));

    await waitFor(() => {
      expect(screen.getByTestId("assistant-empty")).toBeInTheDocument();
    });
  });

  it("shows empty state when no messages", () => {
    renderWithRouter(<AssistantPage />);
    expect(screen.getByTestId("assistant-messages")).toBeInTheDocument();
    expect(screen.getByText(/No questions yet/)).toBeInTheDocument();
  });

  it("shows domain information in response", async () => {
    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");
    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("chat-domains")).toBeInTheDocument();
    });
  });

  it("disables input and submit while loading", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");
    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    expect(input).toBeDisabled();
    expect(submitButton).toBeDisabled();
  });
});

describe("BusinessAssistantPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.assistantAsk).mockResolvedValue(mockAnswerResponse as never);
    vi.mocked(api.assistantAskStream).mockImplementation(async (query, handlers) => {
      handlers?.onMeta?.({
        question: query,
        tools_used: [],
        sources: [],
        verification: mockAnswerResponse.verification,
        grounded: true,
        mode: "tools+rag",
      });
      handlers?.onDelta?.(mockAnswerResponse.answer);
      return vi.mocked(api.assistantAsk)(query) as never;
    });
  });

  it("renders the business assistant with suggestions", () => {
    renderWithRouter(<BusinessAssistantPage />);
    expect(screen.getByText("Business Tax Assistant")).toBeInTheDocument();
    expect(screen.getByTestId("biz-assistant-input")).toBeInTheDocument();
    expect(screen.getAllByTestId("biz-assistant-suggestion").length).toBeGreaterThan(0);
    expect(screen.getByTestId("biz-assistant-empty")).toBeInTheDocument();
  });

  it("submits a suggestion chip directly", async () => {
    const user = userEvent.setup();
    renderWithRouter(<BusinessAssistantPage />);

    await user.click(screen.getAllByTestId("biz-assistant-suggestion")[0]);

    await waitFor(() => {
      expect(screen.getByTestId("biz-chat-answer")).toBeInTheDocument();
    });
    expect(screen.getByTestId("biz-chat-source-chips")).toBeInTheDocument();
    expect(screen.getByTestId("biz-chat-copy")).toBeInTheDocument();
  });

  it("types a question and shows the full pipeline response", async () => {
    const user = userEvent.setup();
    renderWithRouter(<BusinessAssistantPage />);

    await user.type(screen.getByTestId("biz-assistant-input"), "Corporate rate?");
    await user.click(screen.getByTestId("biz-assistant-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("biz-chat-assistant")).toBeInTheDocument();
    });
    expect(screen.getByTestId("biz-chat-verification")).toBeInTheDocument();
    expect(screen.getByTestId("biz-chat-domains")).toBeInTheDocument();
  });
});
