import { useState, useCallback } from "react";
import clsx from "clsx";
import { api, type AnswerResponse } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Card } from "@/components/ui/Card";
import { Kv } from "@/components/ui/Kv";
import { Tag } from "@/components/ui/Tag";
import { VerificationPanel } from "@/components/ui/VerificationPanel";

const TAX_TYPES = [
  { value: "income_tax", label: "Income Tax" },
  { value: "sales_tax", label: "Sales Tax" },
  { value: "federal_excise", label: "Federal Excise" },
  { value: "customs", label: "Customs" },
];

const TAXPAYER_TYPES = [
  { value: "individual", label: "Individual" },
  { value: "business", label: "Business" },
];

const QUERY_MAX_LENGTH = 1000;

const TAX_REDUCER_INSTRUCTION = [
  "Identify applicable lawful deductions, exemptions, credits, and allowable expenses for this taxpayer.",
  "For each opportunity state the estimated impact, eligibility conditions, required supporting documents, and the legal basis with section references.",
  "State the estimated current tax liability, potential lawful savings, and key assumptions.",
  "Only lawful tax planning: never suggest concealing income, fabricating expenses, falsifying records, or evading taxes.",
].join(" ");

export const EVASION_WARNING_TEXT =
  "This tool only supports lawful tax planning. It cannot help conceal income, fabricate expenses, falsify records, or evade taxes.";

const NO_EVIDENCE_ANSWERS = [
  "The provided FBR documents do not contain enough information to answer this.",
  "The retrieved evidence does not support a verified answer.",
];

const EVASION_PATTERNS: RegExp[] = [
  /\b(?:hide|hiding|hidden)\s+(?:my\s+|the\s+|this\s+|some\s+|any\s+)?(?:income|revenue|sales|money|profits?|transactions?)\b/i,
  /\b(?:undeclared|unreported|undisclosed|unrecorded)\s+(?:income|revenue|sales|money|profits?|transactions?)\b/i,
  /\bconceal(?:s|ed|ing)?\b/i,
  /\b(?:fake|false|fabricated?|forged?|bogus|fictitious)\s+(?:expenses?|invoices?|receipts?|bills?|records?|documents?|deductions?|books?)\b/i,
  /\bfalsif(?:y|ies|ied|ying)\b/i,
  /\bunder-?report(?:ing|ed|s)?\b/i,
  /\b(?:tax\s+)?(?:evade|evading|evasion)\b/i,
  /\boff[-\s]?the[-\s]?books?\b/i,
  /\b(?:without|not)\s+(?:declaring|reporting|disclosing)\b/i,
  /\bavoid\s+(?:declaring|reporting|filing)\b/i,
  /\b(?:two|dual|double)\s+(?:sets?\s+of|set\s+of)\s+(?:books?|records?|accounts?)\b/i,
  /\bshow\s+(?:less|lower|reduced)\s+(?:income|revenue|sales|profit)/i,
];

interface TaxReducerFormValues {
  taxYear: string;
  taxType: string;
  taxpayerType: string;
  income: string;
  taxPaid: string;
  allowableExpenses: string;
  investments: string;
  donations: string;
  businessExpenses: string;
  deductions: string;
  exemptions: string;
  otherInfo: string;
}

interface BackendCalculation {
  kind?: string;
  percent?: number;
  amount?: number;
  expression?: string;
  result?: number;
}

interface ScenarioRun {
  id: number;
  label: string;
  form: TaxReducerFormValues;
  result: AnswerResponse;
  calculation: BackendCalculation | null;
}

function emptyForm(): TaxReducerFormValues {
  return {
    taxYear: new Date().getFullYear().toString(),
    taxType: "income_tax",
    taxpayerType: "individual",
    income: "",
    taxPaid: "",
    allowableExpenses: "",
    investments: "",
    donations: "",
    businessExpenses: "",
    deductions: "",
    exemptions: "",
    otherInfo: "",
  };
}

function detectEvasionIntent(...texts: string[]): boolean {
  return texts.some(
    (t) => t.trim().length > 0 && EVASION_PATTERNS.some((re) => re.test(t)),
  );
}

function hasFinancialInformation(form: TaxReducerFormValues): boolean {
  return Boolean(
    form.income ||
      form.taxPaid ||
      form.allowableExpenses ||
      form.investments ||
      form.donations ||
      form.businessExpenses ||
      form.deductions.trim() ||
      form.exemptions.trim() ||
      form.otherInfo.trim(),
  );
}

function buildTaxReducerQuery(form: TaxReducerFormValues): string {
  const who = form.taxpayerType === "business" ? "a business" : "an individual";
  const taxType =
    TAX_TYPES.find((t) => t.value === form.taxType)?.label ?? form.taxType;

  const facts: string[] = [
    `Lawful tax reduction analysis for ${who} under ${taxType} for tax year ${form.taxYear}.`,
  ];
  if (form.income) facts.push(`Annual income: PKR ${form.income}.`);
  if (form.taxPaid) facts.push(`Tax already paid: PKR ${form.taxPaid}.`);
  if (form.allowableExpenses)
    facts.push(`Allowable expenses: PKR ${form.allowableExpenses}.`);
  if (form.investments) facts.push(`Investments: PKR ${form.investments}.`);
  if (form.donations) facts.push(`Donations: PKR ${form.donations}.`);
  if (form.businessExpenses)
    facts.push(`Business expenses: PKR ${form.businessExpenses}.`);

  const notes: string[] = [];
  if (form.deductions.trim())
    notes.push(`Applicable deductions: ${form.deductions.trim()}`);
  if (form.exemptions.trim())
    notes.push(`Applicable exemptions: ${form.exemptions.trim()}`);
  if (form.otherInfo.trim())
    notes.push(`Other relevant information: ${form.otherInfo.trim()}`);

  const head = facts.join(" ");
  const budget =
    QUERY_MAX_LENGTH - head.length - TAX_REDUCER_INSTRUCTION.length - 2;
  let notesText = notes.join(". ");
  if (notesText.length > 0) notesText += ".";
  if (notesText.length > budget) {
    notesText = notesText.slice(0, Math.max(0, budget)).trimEnd();
  }

  const parts =
    budget > 0 && notesText
      ? [head, notesText, TAX_REDUCER_INSTRUCTION]
      : [head, TAX_REDUCER_INSTRUCTION];
  return parts.join(" ").slice(0, QUERY_MAX_LENGTH);
}

function extractCalculation(resp: AnswerResponse): BackendCalculation | null {
  for (const entry of resp.domain_results) {
    if (!entry || typeof entry !== "object") continue;
    if (entry["domain"] !== "calculation") continue;
    const calc = entry["calculation"];
    if (
      calc &&
      typeof calc === "object" &&
      typeof (calc as BackendCalculation).result === "number"
    ) {
      return calc as BackendCalculation;
    }
  }
  return null;
}

function scenarioLabel(index: number): string {
  return String.fromCharCode(65 + (index % 26));
}

function taxTypeLabel(value: string): string {
  return TAX_TYPES.find((t) => t.value === value)?.label ?? value;
}

function taxpayerLabel(value: string): string {
  return value === "business" ? "Business" : "Individual";
}

function formatPkr(value: number): string {
  return `PKR ${value.toLocaleString("en-US")}`;
}

export function TaxReducerPage() {
  const [form, setForm] = useState<TaxReducerFormValues>(emptyForm);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [missingInfo, setMissingInfo] = useState(false);
  const [evasionBlocked, setEvasionBlocked] = useState(false);
  const [taxYearError, setTaxYearError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioRun[]>([]);
  const [activeScenarioId, setActiveScenarioId] = useState<number | null>(null);

  const active = scenarios.find((s) => s.id === activeScenarioId) ?? null;

  const handleChange =
    <K extends keyof TaxReducerFormValues>(
      field: K,
    ) =>
    (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >,
    ) => {
      const value = e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const analyze = useCallback(async () => {
    setTaxYearError(null);
    setMissingInfo(false);
    setEvasionBlocked(false);
    setUnavailable(false);

    if (detectEvasionIntent(form.deductions, form.exemptions, form.otherInfo)) {
      setEvasionBlocked(true);
      return;
    }
    if (!form.taxYear.trim()) {
      setTaxYearError("Tax year is required.");
      return;
    }
    if (!hasFinancialInformation(form)) {
      setMissingInfo(true);
      return;
    }

    const query = buildTaxReducerQuery(form);

    setLoading(true);
    try {
      const resp = await api.answer(query);
      const run: ScenarioRun = {
        id: Date.now(),
        label: scenarioLabel(scenarios.length),
        form: { ...form },
        result: resp,
        calculation: extractCalculation(resp),
      };
      setScenarios((prev) => [...prev, run]);
      setActiveScenarioId(run.id);
    } catch {
      setUnavailable(true);
    } finally {
      setLoading(false);
    }
  }, [form, scenarios.length]);

  const reset = useCallback(() => {
    setForm(emptyForm());
    setUnavailable(false);
    setMissingInfo(false);
    setEvasionBlocked(false);
    setTaxYearError(null);
    setScenarios([]);
    setActiveScenarioId(null);
  }, []);

  const isRefusal = active
    ? NO_EVIDENCE_ANSWERS.includes(active.result.answer.trim())
    : false;

  return (
    <ErrorBoundary>
      <section className="page page--tax-reducer">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Tax Reducer</div>
            <h2 className="page__title">Tax Reducer</h2>
            <p className="page__subtitle">
            Find lawful ways to reduce your tax liability.
          </p>
          </div>
        </header>

        <div className="page__content">
          <Card
            title="Lawful tax planning, not tax evasion"
            testId="tax-reducer-intro"
          >
            <p className="taxreducer__intro-text">
              Tax Reducer reviews your financial information, applicable tax
              rules, deductions, exemptions, credits, and allowable expenses to
              identify legitimate tax-saving opportunities.
            </p>
            <p className="taxreducer__intro-text">
              This tool only supports legal tax optimization — it will never
              suggest hiding income, fabricating expenses, or falsifying
              records. For general tax questions, keep using the AI Tax
              Assistant; Tax Reducer is specialized for structured analysis of
              your own tax position.
            </p>
          </Card>

          <Card
            title="Your tax information"
            subtitle="Fill in what you know — partial information is fine. The backend performs all analysis and calculations."
            testId="tax-reducer-form-card"
          >
            <form
              className="taxreducer-form"
              onSubmit={(e) => {
                e.preventDefault();
                void analyze();
              }}
              data-testid="tax-reducer-form"
            >
              <div className="grid grid--2">
                <Field
                  label="Tax Year"
                  helperText="e.g. 2024, 2025"
                  error={taxYearError ?? undefined}
                  data-testid="tax-reducer-tax-year"
                >
                  <input
                    type="number"
                    min={2020}
                    max={2030}
                    value={form.taxYear}
                    onChange={handleChange("taxYear")}
                    data-testid="tax-reducer-tax-year-input"
                  />
                </Field>

                <Field
                  label="Tax Type"
                  helperText="Which tax the analysis applies to"
                  data-testid="tax-reducer-tax-type"
                >
                  <Select
                    value={form.taxType}
                    onChange={(v) => setForm((prev) => ({ ...prev, taxType: v }))}
                    testId="tax-reducer-tax-type-select"
                    ariaLabel="Tax type"
                    options={TAX_TYPES}
                  />
                </Field>

                <Field
                  label="Taxpayer"
                  helperText="Individual or business"
                  data-testid="tax-reducer-taxpayer"
                >
                  <Select
                    value={form.taxpayerType}
                    onChange={(v) => setForm((prev) => ({ ...prev, taxpayerType: v }))}
                    testId="tax-reducer-taxpayer-select"
                    ariaLabel="Taxpayer"
                    options={TAXPAYER_TYPES}
                  />
                </Field>

                <Field
                  label="Annual Income (PKR)"
                  helperText="Total income for the tax year"
                  data-testid="tax-reducer-income"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.income}
                    onChange={handleChange("income")}
                    data-testid="tax-reducer-income-input"
                  />
                </Field>

                <Field
                  label="Tax Already Paid (PKR)"
                  helperText="Withholding or advance tax paid"
                  data-testid="tax-reducer-tax-paid"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.taxPaid}
                    onChange={handleChange("taxPaid")}
                    data-testid="tax-reducer-tax-paid-input"
                  />
                </Field>

                <Field
                  label="Allowable Expenses (PKR)"
                  helperText="Expenses you can legally claim"
                  data-testid="tax-reducer-allowable-expenses"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.allowableExpenses}
                    onChange={handleChange("allowableExpenses")}
                    data-testid="tax-reducer-allowable-expenses-input"
                  />
                </Field>

                <Field
                  label="Investments (PKR)"
                  helperText="e.g. qualifying funds, savings"
                  data-testid="tax-reducer-investments"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.investments}
                    onChange={handleChange("investments")}
                    data-testid="tax-reducer-investments-input"
                  />
                </Field>

                <Field
                  label="Donations (PKR)"
                  helperText="Charitable donations made"
                  data-testid="tax-reducer-donations"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.donations}
                    onChange={handleChange("donations")}
                    data-testid="tax-reducer-donations-input"
                  />
                </Field>

                <Field
                  label="Business Expenses (PKR)"
                  helperText="If you run a business"
                  data-testid="tax-reducer-business-expenses"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.businessExpenses}
                    onChange={handleChange("businessExpenses")}
                    data-testid="tax-reducer-business-expenses-input"
                  />
                </Field>

                <Field
                  label="Applicable Deductions"
                  helperText="Deductions you believe apply (optional)"
                  data-testid="tax-reducer-deductions"
                >
                  <input
                    type="text"
                    value={form.deductions}
                    onChange={handleChange("deductions")}
                    placeholder="e.g. Zakat, donations under Section 61"
                    data-testid="tax-reducer-deductions-input"
                  />
                </Field>

                <Field
                  label="Applicable Exemptions"
                  helperText="Exemptions you believe apply (optional)"
                  data-testid="tax-reducer-exemptions"
                >
                  <input
                    type="text"
                    value={form.exemptions}
                    onChange={handleChange("exemptions")}
                    placeholder="e.g. teacher/researcher exemption"
                    data-testid="tax-reducer-exemptions-input"
                  />
                </Field>
              </div>

              <Field
                label="Other Relevant Information"
                helperText="Anything else that affects your tax position"
                data-testid="tax-reducer-other-info"
              >
                <textarea
                  rows={3}
                  value={form.otherInfo}
                  onChange={handleChange("otherInfo")}
                  placeholder="e.g. salary income with tax withheld at source, property income, freelancer receipts"
                  data-testid="tax-reducer-other-info-input"
                />
              </Field>

              <div className="form__actions">
                <Button
                  type="submit"
                  variant="primary"
                  loading={loading}
                  disabled={loading}
                  data-testid="tax-reducer-analyze-button"
                >
                  {loading ? "Analyzing your tax information…" : "Analyze Tax Position"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={reset}
                  data-testid="tax-reducer-reset-button"
                >
                  Reset
                </Button>
              </div>
            </form>
          </Card>

          {evasionBlocked ? (
            <StatusBanner
              kind="warn"
              title={EVASION_WARNING_TEXT}
              description="Use the fields above to explore lawful deductions, exemptions, credits, and allowable expenses instead."
              action={
                <Button variant="ghost" onClick={() => setEvasionBlocked(false)}>
                  Dismiss
                </Button>
              }
              testId="tax-reducer-evasion-warning"
            />
          ) : null}

          {missingInfo ? (
            <StatusBanner
              kind="warn"
              title="More information is required to estimate this accurately."
              description="Provide at least your income, expenses, investments, donations, or notes about your tax situation, then run the analysis again."
              testId="tax-reducer-missing-info"
            />
          ) : null}

          {unavailable ? (
            <StatusBanner
              kind="err"
              title="Tax analysis is temporarily unavailable."
              testId="tax-reducer-error"
            />
          ) : null}

          {loading ? (
            <StatusBanner
              kind="info"
              title="Analyzing your tax information…"
              description="The backend is reviewing applicable tax rules against the information you provided."
              testId="tax-reducer-loading"
            />
          ) : null}

          {active && !loading ? (
            <div className="taxreducer-result" data-testid="tax-reducer-result">
              <Card
                title="Lawful tax-saving opportunities (estimated)"
                subtitle={`Scenario ${active.label} · based on the information provided`}
                action={<Tag variant="accent">Estimate</Tag>}
                testId="tax-reducer-analysis-card"
              >
                <p
                  className="taxreducer__estimate-note"
                  data-testid="tax-reducer-estimate-note"
                >
                  Estimated figures are based on the information provided and
                  are subject to eligibility. Savings are potential, not
                  guaranteed.
                </p>
                {isRefusal ? (
                  <StatusBanner
                    kind="info"
                    title="No additional lawful tax-saving opportunities were identified from the information provided."
                    description="Add more financial detail above and run the analysis again."
                    testId="tax-reducer-no-opportunities"
                  />
                ) : (
                  <div
                    className="taxreducer__analysis"
                    data-testid="tax-reducer-analysis"
                  >
                    {active.result.answer}
                  </div>
                )}
              </Card>

              <Card title="Analysis summary" testId="tax-reducer-summary-card">
                <Kv
                  rows={[
                    { key: "Tax year", value: active.form.taxYear },
                    {
                      key: "Taxpayer",
                      value: taxpayerLabel(active.form.taxpayerType),
                    },
                    {
                      key: "Tax type",
                      value: taxTypeLabel(active.form.taxType),
                    },
                    {
                      key: "Income provided",
                      value: active.form.income
                        ? formatPkr(Number(active.form.income))
                        : "Not provided",
                    },
                    ...(active.calculation?.result != null
                      ? [
                          {
                            key: "Estimated calculation (backend)",
                            value: formatPkr(active.calculation.result),
                          },
                          ...(active.calculation.expression
                            ? [
                                {
                                  key: "Calculation basis",
                                  value: active.calculation.expression,
                                },
                              ]
                            : []),
                        ]
                      : []),
                  ]}
                  testId="tax-reducer-summary"
                />
              </Card>

              <Card
                title="Confidence & verification"
                testId="tax-reducer-verification-card"
              >
                <VerificationPanel
                  verification={active.result.verification}
                  grounded={active.result.grounded}
                  testId="tax-reducer-verification"
                />
              </Card>

              <Card
                title="Independence notice"
                testId="tax-reducer-disclaimer-card"
              >
                <p className="calc-disclaimer__text">
                  These suggestions are AI-generated from official FBR law and are not tax
                  advice. Eligibility and savings are estimates — please verify each option
                  independently with the relevant Finance Act provisions or a licensed tax
                  practitioner before acting on it.
                </p>
              </Card>

              <Card
                title="Legal sources"
                testId="tax-reducer-sources-card"
              >
                {active.result.sources.length > 0 ? (
                  <SourceList
                    sources={active.result.sources}
                    testId="tax-reducer-sources"
                  />
                ) : (
                  <p className="muted" data-testid="tax-reducer-no-sources">
                    Source not available
                  </p>
                )}
              </Card>
            </div>
          ) : null}

          {scenarios.length > 0 ? (
            <Card
              title="Scenario comparison"
              subtitle="Each analysis run is kept as a scenario. Run the analysis again with different inputs to compare lawful options. Differences are shown only where the backend returned a calculated result."
              testId="tax-reducer-scenarios"
            >
              <div className="taxreducer__scenarios">
                {scenarios.map((s, idx) => {
                  const baseline = scenarios[0];
                  const diff =
                    idx > 0 &&
                    s.calculation?.result != null &&
                    baseline.calculation?.result != null
                      ? s.calculation.result - baseline.calculation.result
                      : null;
                  const isActive = s.id === activeScenarioId;
                  return (
                    <div
                      key={s.id}
                      className={clsx(
                        "taxreducer__scenario",
                        isActive && "taxreducer__scenario--active",
                      )}
                      data-testid={`tax-reducer-scenario-${s.label}`}
                    >
                      <Kv
                        rows={[
                          {
                            key: `Scenario ${s.label}${
                              idx === 0 ? " (current situation)" : ""
                            }`,
                            value: `${taxpayerLabel(
                              s.form.taxpayerType,
                            )} · tax year ${s.form.taxYear} · ${
                              s.form.income
                                ? `income ${formatPkr(Number(s.form.income))}`
                                : "income not provided"
                            }`,
                          },
                          ...(s.calculation?.result != null
                            ? [
                                {
                                  key: "Calculated result (backend)",
                                  value: formatPkr(s.calculation.result),
                                },
                              ]
                            : []),
                          ...(diff != null
                            ? [
                                {
                                  key: "Difference vs Scenario A",
                                  value: formatPkr(diff),
                                },
                              ]
                            : []),
                          {
                            key: "Verified",
                            value: (
                              <Tag
                                variant={
                                  s.result.verification.passed ? "ok" : "err"
                                }
                              >
                                {s.result.verification.passed
                                  ? "Verified"
                                  : "Not verified"}
                              </Tag>
                            ),
                          },
                          {
                            key: "Grounded",
                            value: (
                              <Tag variant={s.result.grounded ? "ok" : "warn"}>
                                {s.result.grounded ? "Yes" : "No"}
                              </Tag>
                            ),
                          },
                        ]}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setActiveScenarioId(s.id)}
                        data-testid={`tax-reducer-scenario-view-${s.label}`}
                      >
                        {isActive ? "Viewing" : "View analysis"}
                      </Button>
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : null}
        </div>
      </section>
    </ErrorBoundary>
  );
}
