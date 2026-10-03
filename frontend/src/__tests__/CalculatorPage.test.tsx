import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { CalculatorPage } from "../pages/personal/CalculatorPage";
import { api } from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      health: vi.fn(),
      answer: vi.fn(),
      calculate: vi.fn(),
    },
  };
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

const mockAnswerResponse = {
  question: "Calculate income tax for tax year 2024 with filing status single. income of 1200000.",
  domains: ["tax", "calculation"],
  primary_domain: "tax",
  multi_domain: false,
  routing: {},
  domain_results: [],
  answer: "Estimated tax: Rs 150,000",
  sources: [
    {
      chunk_id: "c1",
      document_id: "d1",
      source: "Income Tax Ordinance, 2001",
      source_path: "/documents/ito.pdf",
      source_sha256: null,
      page: 10,
      page_start: 50,
      page_end: 100,
      section: "Section 4",
      section_reference: "s4",
      section_number: "4",
      law_tag: "income_tax",
      multi_law_candidate: false,
      score: 0.95,
      semantic_score: 0.9,
      bm25_score: 0.85,
      exact_match: true,
    },
  ],
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

describe("CalculatorPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(mockAnswerResponse);
    vi.mocked(api.calculate).mockResolvedValue({
      success: true,
      calculation_type: "income_tax",
      data: { total_tax: 150000 },
      formatted_text: "Estimated tax: Rs 150,000",
      audit_id: "test-audit",
    });
  });

  it("renders the calculator interface", () => {
    renderWithRouter(<CalculatorPage />);
    expect(screen.getByText("Tax Calculator")).toBeInTheDocument();
    expect(screen.getByTestId("calculator-form")).toBeInTheDocument();
    expect(screen.getByTestId("calculate-button")).toBeInTheDocument();
    expect(screen.getByTestId("reset-button")).toBeInTheDocument();
  });

  it("displays all form fields", () => {
    renderWithRouter(<CalculatorPage />);
    expect(screen.getByTestId("calc-type-select")).toBeInTheDocument();
    expect(screen.getByTestId("tax-year-input")).toBeInTheDocument();
    expect(screen.getByTestId("filing-status-select")).toBeInTheDocument();
    expect(screen.getByTestId("income-input")).toBeInTheDocument();
    expect(screen.getByTestId("deductions-input")).toBeInTheDocument();
    expect(screen.getByTestId("credits-input")).toBeInTheDocument();
    expect(screen.getByTestId("additional-info-input")).toBeInTheDocument();
  });

  it("shows ready state when form has income data", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1200000");

    expect(screen.getByTestId("calculator-ready")).toBeInTheDocument();
  });

  it("calculates tax and displays result", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.click(screen.getByTestId("calc-type-select"));
    await user.click(screen.getByTestId("calc-type-select-option-income_tax"));
    await user.clear(screen.getByTestId("tax-year-input"));
    await user.type(screen.getByTestId("tax-year-input"), "2024");
    await user.click(screen.getByTestId("filing-status-select"));
    await user.click(screen.getByTestId("filing-status-select-option-single"));
    await user.type(screen.getByTestId("income-input"), "1200000");

    await user.click(screen.getByTestId("calculate-button"));

    // Structured card renders the deterministic summary (rich text has
    // replaced the old single <p data-testid="calc-result-amount">).
    await waitFor(() => {
      expect(screen.getByTestId("calc-explanation")).toBeInTheDocument();
    });
    expect(screen.getByTestId("calc-explanation").textContent).toContain("Estimated tax: Rs 150,000");
  });

  it("sends constructed query to the API", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1200000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(api.answer).toHaveBeenCalledTimes(1);
    });
    expect(api.answer).toHaveBeenCalledWith(expect.stringContaining("income of 1200000"));
  });

  it("shows loading state during calculation", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1000000");
    await user.click(screen.getByTestId("calculate-button"));

    expect(screen.getByTestId("calculate-button")).toHaveTextContent("Calculating…");
    expect(screen.getByTestId("calculate-button")).toBeDisabled();
  });

  it("shows error state when API fails", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.calculate).mockRejectedValue(new Error("API Error"));
    vi.mocked(api.answer).mockRejectedValue(new Error("API Error"));

    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1000000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calculator-error")).toBeInTheDocument();
    });
  });

  it("resets form when reset button is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1000000");
    await user.type(screen.getByTestId("deductions-input"), "200000");
    await user.click(screen.getByTestId("calc-type-select"));
    await user.click(screen.getByTestId("calc-type-select-option-sales_tax"));
    await user.click(screen.getByTestId("filing-status-select"));
    await user.click(screen.getByTestId("filing-status-select-option-married_jointly"));

    await user.click(screen.getByTestId("reset-button"));

    expect(screen.getByTestId("income-input")).toHaveValue(null);
    expect(screen.getByTestId("deductions-input")).toHaveValue(null);
    expect(screen.getByTestId("calc-type-select")).toHaveTextContent("Income Tax");
    expect(screen.getByTestId("filing-status-select")).toHaveTextContent("Single");
  });

  it("shows a live cap hint when income exceeds 1 trillion, and blocks submit with an error", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    // Below the cap: no hint.
    await user.type(screen.getByTestId("income-input"), "999000000");
    expect(screen.queryByTestId("income-cap-hint")).not.toBeInTheDocument();

    // Above the cap: hint appears immediately, before submitting.
    await user.clear(screen.getByTestId("income-input"));
    await user.type(screen.getByTestId("income-input"), "1000000000001");
    expect(screen.getByTestId("income-cap-hint")).toBeInTheDocument();

    // Submitting shows a field error instead of calling the API.
    await user.click(screen.getByTestId("calculate-button"));
    expect(await screen.findByText(/exceeds the maximum supported amount/i)).toBeInTheDocument();
    expect(api.calculate).not.toHaveBeenCalled();
  });

  it("shows the independent-verification disclaimer when result is available", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1000000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calc-disclaimer")).toBeInTheDocument();
    });
    // ChatGPT-style guidance: verify results yourself.
    expect(screen.getByText(/verify.*independently/i)).toBeInTheDocument();
    // Deterministic results carry an honest "deterministic engine" verification.
    expect(screen.getByTestId("calc-verification")).toBeInTheDocument();
  });

  it("shows sources when available", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1000000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calc-sources")).toBeInTheDocument();
    });
  });

  it("supports choosing different calculation types", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.click(screen.getByTestId("calc-type-select"));
    await user.click(screen.getByTestId("calc-type-select-option-sales_tax"));
    await user.type(screen.getByTestId("income-input"), "500000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calc-explanation")).toBeInTheDocument();
    });
  });
});
