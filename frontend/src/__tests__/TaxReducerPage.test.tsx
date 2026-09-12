import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TaxReducerPage } from "../pages/personal/TaxReducerPage";
import { AppShell } from "../components/shell/AppShell";
import { PERSONAL_SECTIONS } from "../state/personalNav";

const EVASION_WARNING_TEXT =
  "This tool only supports lawful tax planning. It cannot help conceal income, fabricate expenses, falsify records, or evade taxes.";

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

function StubOverview() {
  return <div data-testid="stub-overview">Overview</div>;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <TaxReducerPage />
    </MemoryRouter>,
  );
}

function renderWithRoutes(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/personal" element={<AppShell />}>
          <Route path="overview" element={<StubOverview />} />
          <Route path="tax-reducer" element={<TaxReducerPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const mockSource = {
  chunk_id: "c1",
  document_id: "d1",
  source: "Income Tax Ordinance, 2001",
  source_path: "/documents/ito.pdf",
  source_sha256: null,
  page: 42,
  page_start: 40,
  page_end: 45,
  section: "Section 61",
  section_reference: "s61",
  section_number: "61",
  law_tag: "income_tax",
  multi_law_candidate: false,
  score: 0.93,
  semantic_score: 0.91,
  bm25_score: 0.88,
  exact_match: true,
};

const mockVerification = {
  passed: true,
  checks: {
    answer_size: { passed: true, reason: "ok" },
    section_consistency: { passed: true, reason: "ok" },
    grounding: { passed: true, reason: "ok" },
    speculation: { passed: true, reason: "ok" },
  },
  failed_checks: [],
  reason: "ok",
};

const mockAnswerText = [
  "Current estimated tax liability: PKR 375,000 (estimated).",
  "",
  "1. Charitable donations deduction",
  "Estimated impact: PKR 112,500 (potential, subject to eligibility).",
  "Eligibility: Donations to approved charitable institutions under Section 61.",
  "Required evidence: Receipts from the approved institution.",
  "Legal basis: Income Tax Ordinance, 2001, Section 61.",
  "",
  "Important assumptions: Based on provided information; full-year rates apply.",
].join("\n");

function makeResponse(overrides: Record<string, unknown> = {}) {
  return {
    question: "Lawful tax reduction analysis",
    domains: ["tax"],
    primary_domain: "tax",
    multi_domain: false,
    routing: {},
    domain_results: [
      {
        domain: "calculation",
        answer: mockAnswerText,
        calculation: {
          kind: "percent_of_amount",
          percent: 15,
          amount: 2500000,
          expression: "2500000 x 15% = 375000",
          result: 375000,
        },
      },
    ],
    answer: mockAnswerText,
    sources: [mockSource],
    verification: mockVerification,
    grounded: true,
    ...overrides,
  };
}

describe("TaxReducerPage — workspace and navigation", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.health).mockResolvedValue({ status: "ok", version: "1.0.0" });
    vi.mocked(api.answer).mockResolvedValue(makeResponse());
  });

  it("registers Tax Reducer in the personal workspace sections", () => {
    const section = PERSONAL_SECTIONS.find((s) => s.id === "tax-reducer");
    expect(section).toBeDefined();
    expect(section?.label).toBe("Tax Reducer");
    expect(section?.blurb).toBe("Find lawful ways to reduce your tax liability.");
    expect(section?.path).toBe("/personal/tax-reducer");
    expect(section?.status).toBe("ready");
  });

  it("shows Tax Reducer as an active item in the personal navigation", () => {
    renderWithRoutes("/personal/tax-reducer");
    const nav = screen.getByTestId("personal-nav");
    const item = nav.querySelector('[data-section="tax-reducer"]');
    expect(item).toBeTruthy();
    expect(item?.className).toContain("sidebar__item--active");
  });

  it("opens Tax Reducer from the sidebar navigation", async () => {
    const user = userEvent.setup();
    renderWithRoutes("/personal/overview");
    await user.click(screen.getByRole("link", { name: "Tax Reducer" }));
    expect(screen.getByTestId("tax-reducer-form")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Tax Reducer" }),
    ).toBeInTheDocument();
  });

  it("renders the introduction panel and primary action", () => {
    const { container } = renderWithRoutes("/personal/tax-reducer");
    expect(
      screen.getByRole("heading", { level: 2, name: "Tax Reducer" }),
    ).toBeInTheDocument();
    const headerSubtitle = container.querySelector(".app-header__subtitle");
    expect(headerSubtitle?.textContent).toBe(
      "Find lawful ways to reduce your tax liability.",
    );
    const pageSubtitle = container.querySelector(
      ".page--tax-reducer .page__subtitle",
    );
    expect(pageSubtitle?.textContent).toBe(
      "Find lawful ways to reduce your tax liability.",
    );
    expect(screen.getByTestId("tax-reducer-intro")).toBeInTheDocument();
    expect(screen.getByTestId("tax-reducer-analyze-button")).toHaveTextContent(
      "Analyze Tax Position",
    );
  });
});

describe("TaxReducerPage — form and validation", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(makeResponse());
  });

  it("renders the input form with all fields", () => {
    renderPage();
    const testIds = [
      "tax-reducer-tax-year-input",
      "tax-reducer-tax-type-select",
      "tax-reducer-taxpayer-select",
      "tax-reducer-income-input",
      "tax-reducer-tax-paid-input",
      "tax-reducer-allowable-expenses-input",
      "tax-reducer-investments-input",
      "tax-reducer-donations-input",
      "tax-reducer-business-expenses-input",
      "tax-reducer-deductions-input",
      "tax-reducer-exemptions-input",
      "tax-reducer-other-info-input",
    ];
    for (const id of testIds) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
  });

  it("requires the tax year before analysis", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderPage();

    await user.clear(screen.getByTestId("tax-reducer-tax-year-input"));
    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");

    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    expect(screen.getByText("Tax year is required.")).toBeInTheDocument();
    expect(api.answer).not.toHaveBeenCalled();
  });

  it("shows the missing-information state when nothing is provided", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    const banner = screen.getByTestId("tax-reducer-missing-info");
    expect(banner).toHaveTextContent(
      "More information is required to estimate this accurately.",
    );
    expect(api.answer).not.toHaveBeenCalled();
  });

  it("continues with partial information", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");

    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(api.answer).toHaveBeenCalledTimes(1);
    });
  });

  it("forms a lawful analysis query within the backend length limit", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(
      screen.getByTestId("tax-reducer-taxpayer-select"),
      "business",
    );
    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.type(
      screen.getByTestId("tax-reducer-other-info-input"),
      "Salary income with tax withheld at source.",
    );

    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(api.answer).toHaveBeenCalledTimes(1);
    });
    const query = vi.mocked(api.answer).mock.calls[0][0];
    expect(query.length).toBeLessThanOrEqual(1000);
    expect(query).toContain("Lawful tax reduction analysis");
    expect(query).toContain("2500000");
    expect(query).toContain("business");
    expect(query).toContain("tax withheld at source");
    expect(query.toLowerCase()).toContain("lawful tax planning");
  });

  it("resets the form and results", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-result")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("tax-reducer-reset-button"));

    expect(screen.getByTestId("tax-reducer-income-input")).toHaveValue(null);
    expect(screen.queryByTestId("tax-reducer-result")).not.toBeInTheDocument();
  });
});

describe("TaxReducerPage — loading, errors, and legal safety", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(makeResponse());
  });

  it("shows the loading state while analyzing", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "1000000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    expect(screen.getByTestId("tax-reducer-analyze-button")).toBeDisabled();
    expect(screen.getByTestId("tax-reducer-analyze-button")).toHaveTextContent(
      "Analyzing your tax information",
    );
    expect(screen.getByTestId("tax-reducer-loading")).toBeInTheDocument();
  });

  it("shows the backend-unavailable state on API failure", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockRejectedValue(new Error("network down"));

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "1000000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    const banner = await screen.findByTestId("tax-reducer-error");
    expect(banner).toHaveTextContent(
      "Tax analysis is temporarily unavailable. Please try again.",
    );
    expect(banner.textContent).not.toContain("network down");
  });

  it("blocks unlawful tax-evasion requests instead of analyzing them", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByTestId("tax-reducer-other-info-input"),
      "How can I hide my income from FBR and evade taxes?",
    );

    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    const warning = screen.getByTestId("tax-reducer-evasion-warning");
    expect(warning).toHaveTextContent(EVASION_WARNING_TEXT);
    expect(api.answer).not.toHaveBeenCalled();
    expect(screen.queryByTestId("tax-reducer-result")).not.toBeInTheDocument();
  });
});

describe("TaxReducerPage — results", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(makeResponse());
  });

  it("renders the successful result dashboard", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-result")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tax-reducer-analysis-card")).toBeInTheDocument();
    expect(screen.getByTestId("tax-reducer-summary")).toBeInTheDocument();
    expect(screen.getByTestId("tax-reducer-verification")).toBeInTheDocument();
  });

  it("renders estimated savings together with the estimate caveat", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-analysis")).toBeInTheDocument();
    });
    expect(screen.getByText(/Estimated impact: PKR 112,500/)).toBeInTheDocument();
    expect(screen.getByTestId("tax-reducer-estimate-note")).toHaveTextContent(
      "subject to eligibility",
    );
  });

  it("renders eligibility, evidence, and legal basis from the analysis", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-analysis")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Eligibility: Donations to approved charitable institutions/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Required evidence: Receipts/)).toBeInTheDocument();
    expect(screen.getByText(/Legal basis: Income Tax Ordinance, 2001/)).toBeInTheDocument();
  });

  it("renders legal sources with citation details", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-sources")).toBeInTheDocument();
    });
    expect(screen.getByText("Income Tax Ordinance, 2001")).toBeInTheDocument();
  });

  it("marks sources as unavailable when the backend returns none", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(makeResponse({ sources: [] }));

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-no-sources")).toBeInTheDocument();
    });
    expect(screen.getByText("Source not available")).toBeInTheDocument();
  });

  it("shows the no-opportunities state when no lawful savings are found", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer).mockResolvedValue(
      makeResponse({
        answer:
          "The provided FBR documents do not contain enough information to answer this.",
        domain_results: [],
      }),
    );

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    const banner = await screen.findByTestId("tax-reducer-no-opportunities");
    expect(banner).toHaveTextContent(
      "No additional lawful tax-saving opportunities were identified from the information provided.",
    );
    expect(screen.queryByTestId("tax-reducer-analysis")).not.toBeInTheDocument();
  });

  it("keeps scenario history and compares backend-calculated results", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer)
      .mockResolvedValueOnce(makeResponse())
      .mockResolvedValueOnce(
        makeResponse({
          answer: "Optimized analysis with deduction applied.",
          domain_results: [
            {
              domain: "calculation",
              answer: "Optimized analysis with deduction applied.",
              calculation: {
                kind: "percent_of_amount",
                percent: 12,
                amount: 2500000,
                expression: "2500000 x 12% = 300000",
                result: 300000,
              },
            },
          ],
        }),
      );

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-result")).toBeInTheDocument();
    });

    await user.clear(screen.getByTestId("tax-reducer-income-input"));
    await user.type(screen.getByTestId("tax-reducer-income-input"), "3000000");
    await user.type(
      screen.getByTestId("tax-reducer-deductions-input"),
      "Donations under Section 61",
    );
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(api.answer).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-scenario-A")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tax-reducer-scenario-B")).toBeInTheDocument();

    const scenarioB = within(screen.getByTestId("tax-reducer-scenario-B"));
    expect(
      scenarioB.getByText("Difference vs Scenario A"),
    ).toBeInTheDocument();
    expect(scenarioB.getByText(/-75,000/)).toBeInTheDocument();
  });

  it("redisplays a previous scenario from the comparison list", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.answer)
      .mockResolvedValueOnce(makeResponse())
      .mockResolvedValueOnce(
        makeResponse({ answer: "Second scenario analysis text." }),
      );

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-result")).toBeInTheDocument();
    });

    await user.clear(screen.getByTestId("tax-reducer-income-input"));
    await user.type(screen.getByTestId("tax-reducer-income-input"), "3000000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(api.answer).toHaveBeenCalledTimes(2);
    });

    expect(screen.getByText("Second scenario analysis text.")).toBeInTheDocument();

    await user.click(screen.getByTestId("tax-reducer-scenario-view-A"));

    expect(screen.getByText(/Current estimated tax liability/)).toBeInTheDocument();
    expect(
      screen.queryByText("Second scenario analysis text."),
    ).not.toBeInTheDocument();
  });

  it("uses the responsive design-system grid and stacked result layout", async () => {
    const { container } = renderPage();
    expect(container.querySelector(".taxreducer-form .grid--2")).toBeTruthy();

    const user = userEvent.setup();
    await user.type(screen.getByTestId("tax-reducer-income-input"), "2500000");
    await user.click(screen.getByTestId("tax-reducer-analyze-button"));

    await waitFor(() => {
      expect(screen.getByTestId("tax-reducer-result")).toBeInTheDocument();
    });
    expect(container.querySelector(".taxreducer-result")).toBeTruthy();
    expect(container.querySelector(".taxreducer__scenarios")).toBeTruthy();
  });
});
