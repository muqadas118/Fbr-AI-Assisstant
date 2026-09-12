import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { AssistantPage } from "../pages/personal/AssistantPage";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      health: vi.fn(),
      answer: vi.fn(),
    },
  };
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

const mockAnswerResponse = {
  question: "What is the penalty for late filing?",
  domains: ["tax", "compliance"],
  primary_domain: "tax",
  multi_domain: false,
  routing: {},
  domain_results: [],
  answer: "The penalty for late filing is 0.5% per month.",
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
};

describe("AssistantPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(mockAnswerResponse);
  });

  it("renders the assistant interface", () => {
    renderWithRouter(<AssistantPage />);
    expect(screen.getByText("AI Tax Assistant")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-input")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-form")).toBeInTheDocument();
    expect(
      screen.getByText(
        "No questions yet. Ask anything about FBR tax, filing obligations, notice types, or compliance timelines.",
      ),
    ).toBeInTheDocument();
  });

  it("displays the subtitle explaining the verified pipeline", () => {
    renderWithRouter(<AssistantPage />);
    expect(screen.getByText(/verified backend pipeline/)).toBeInTheDocument();
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
  });

  it("shows loading state during API call", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");

    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    expect(screen.getByTestId("assistant-loading")).toBeInTheDocument();
  });

  it("shows error state when API fails", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockRejectedValue(new Error("Network failure"));

    const user = userEvent.setup();
    renderWithRouter(<AssistantPage />);

    const input = screen.getByTestId("assistant-input");
    await user.type(input, "Test query");

    const submitButton = screen.getByTestId("assistant-submit");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByTestId("chat-error")).toBeInTheDocument();
    });
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
      expect(
        screen.getByText(
          "No questions yet. Ask anything about FBR tax, filing obligations, notice types, or compliance timelines.",
        ),
      ).toBeInTheDocument();
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
    vi.mocked(api.answer).mockImplementation(() => new Promise(() => {}));

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
