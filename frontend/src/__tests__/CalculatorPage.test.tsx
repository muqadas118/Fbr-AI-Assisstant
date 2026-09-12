import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { CalculatorPage } from "../pages/personal/CalculatorPage";

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

    await user.selectOptions(screen.getByTestId("calc-type-select"), "income_tax");
    await user.clear(screen.getByTestId("tax-year-input"));
    await user.type(screen.getByTestId("tax-year-input"), "2024");
    await user.selectOptions(screen.getByTestId("filing-status-select"), "single");
    await user.type(screen.getByTestId("income-input"), "1200000");

    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calc-result-amount")).toBeInTheDocument();
    });
    expect(screen.getByText("Estimated tax: Rs 150,000")).toBeInTheDocument();
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
    await user.selectOptions(screen.getByTestId("calc-type-select"), "sales_tax");
    await user.selectOptions(screen.getByTestId("filing-status-select"), "married_jointly");

    await user.click(screen.getByTestId("reset-button"));

    expect(screen.getByTestId("income-input")).toHaveValue(null);
    expect(screen.getByTestId("deductions-input")).toHaveValue(null);
    expect(screen.getByTestId("calc-type-select")).toHaveValue("income_tax");
    expect(screen.getByTestId("filing-status-select")).toHaveValue("single");
  });

  it("shows verification panel when result is available", async () => {
    const user = userEvent.setup();
    renderWithRouter(<CalculatorPage />);

    await user.type(screen.getByTestId("income-input"), "1000000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calc-verification")).toBeInTheDocument();
    });
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

    await user.selectOptions(screen.getByTestId("calc-type-select"), "sales_tax");
    await user.type(screen.getByTestId("income-input"), "500000");
    await user.click(screen.getByTestId("calculate-button"));

    await waitFor(() => {
      expect(screen.getByTestId("calc-result-amount")).toBeInTheDocument();
    });
  });
});
