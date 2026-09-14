import { useState, useCallback } from "react";
import clsx from "clsx";
import { api, type AnswerResponse } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { VerificationPanel } from "@/components/ui/VerificationPanel";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Card } from "@/components/ui/Card";
import { Kv } from "@/components/ui/Kv";
import { Tag } from "@/components/ui/Tag";

const TAX_TYPES = [
  { value: "income_tax", label: "Corporate / AOP Income Tax" },
  { value: "sales_tax", label: "Sales Tax" },
  { value: "withholding_tax", label: "Withholding Tax" },
  { value: "federal_excise", label: "Federal Excise" },
  { value: "customs", label: "Customs" },
];

const TAXPAYER_TYPES = [
  { value: "company", label: "Company" },
  { value: "aop", label: "Association of Persons (AOP)" },
  { value: "business", label: "Sole Proprietorship / Registered Business" },
];

const QUERY_MAX_LENGTH = 1000;

const TAX_REDUCER_INSTRUCTION = [
  "Identify applicable lawful business deductions, exemptions, depreciation allowances, and input-tax adjustments for this company or business.",
  "For each opportunity state the estimated impact, eligibility conditions, required supporting documents, and the legal basis with section references.",
  "State the estimated current tax liability, potential lawful savings, and key assumptions.",
  "Only lawful tax planning: never suggest concealing income, fabricating expenses, falsifying records, or evading taxes.",
].join(" ");

export const EVASION_WARNING_TEXT =
  "This tool only supports lawful business tax planning. It cannot help conceal income, fabricate expenses, falsify records, or evade taxes.";

const NO_EVIDENCE_ANSWERS = [
  "The provided FBR documents do not contain enough information to answer this.",
  "The retrieved evidence does not support a verified answer.",
];

const EVASION_PATTERNS: RegExp[] = [
  /\b(?:hide|hiding|hidden)\s+(?:my\s+|the\s+|this\s+|some\s+|any\s+)?(?:income|revenue|sales|money|profits?|transactions?|turnover)\b/i,
  /\b(?:undeclared|unreported|undisclosed|unrecorded)\s+(?:income|revenue|sales|money|profits?|transactions?|turnover)\b/i,
  /\bconceal(?:s|ed|ing)?\b/i,
  /\b(?:fake|false|fabricated?|forged?|bogus|fictitious)\s+(?:expenses?|invoices?|receipts?|bills?|records?|documents?|deductions?|books?)\b/i,
  /\bfalsif(?:y|ies|ied|ying)\b/i,
  /\bunder-?report(?:ing|ed|s)?\b/i,
  /\b(?:tax\s+)?(?:evade|evading|evasion)\b/i,
  /\boff[-\s]?the[-\s]?books?\b/i,
  /\b(?:without|not)\s+(?:declaring|reporting|disclosing)\b/i,
  /\bavoid\s+(?:declaring|reporting|filing)\b/i,
  /\b(?:two|dual|double)\s+(?:sets?\s+of|set\s+of)\s+(?:books?|records?|accounts?)\b/i,
  /\bshow\s+(?:less|lower|reduced)\s+(?:income|revenue|sales|profit|turnover)/i,
];

interface TaxReducerFormValues {
  taxYear: string;
  taxType: string;
  taxpayerType: string;
  turnover: string;
  taxPaid: string;
  businessExpenses: string;
  depreciation: string;
  capitalExpenditure: string;
  inputTaxPaid: string;
  outputTaxCollected: string;
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
    taxpayerType: "company",
    turnover: "",
    taxPaid: "",
    businessExpenses: "",
    depreciation: "",
    capitalExpenditure: "",
    inputTaxPaid: "",
    outputTaxCollected: "",
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
    form.turnover ||
      form.taxPaid ||
      form.businessExpenses ||
      form.depreciation ||
      form.capitalExpenditure ||
      form.inputTaxPaid ||
      form.outputTaxCollected ||
      form.deductions.trim() ||
      form.exemptions.trim() ||
      form.otherInfo.trim(),
  );
}

function buildTaxReducerQuery(form: TaxReducerFormValues): string {
  const taxpayer =
    TAXPAYER_TYPES.find((t) => t.value === form.taxpayerType)?.label ??
    form.taxpayerType;
  const taxType =
    TAX_TYPES.find((t) => t.value === form.taxType)?.label ?? form.taxType;

  const facts: string[] = [
    `Lawful tax reduction analysis for a ${taxpayer} under ${taxType} for tax year ${form.taxYear}.`,
  ];
  if (form.turnover) facts.push(`Annual turnover: PKR ${form.turnover}.`);
  if (form.taxPaid) facts.push(`Tax already paid: PKR ${form.taxPaid}.`);
  if (form.businessExpenses)
    facts.push(`Allowable business expenses: PKR ${form.businessExpenses}.`);
  if (form.depreciation)
    facts.push(`Depreciation claimed: PKR ${form.depreciation}.`);
  if (form.capitalExpenditure)
    facts.push(`Capital expenditure on fixed assets: PKR ${form.capitalExpenditure}.`);
  if (form.inputTaxPaid)
    facts.push(`Sales tax input paid on purchases: PKR ${form.inputTaxPaid}.`);
  if (form.outputTaxCollected)
    facts.push(`Sales tax output collected on sales: PKR ${form.outputTaxCollected}.`);

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
  return TAXPAYER_TYPES.find((t) => t.value === value)?.label ?? value;
}

function formatPkr(value: number): string {
  return `PKR ${value.toLocaleString("en-US")}`;
}

export function BusinessTaxReducerPage() {
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
          <p className="page-eyebrow">Business · Tax Planning</p>
          <h2 className="page__title">Business Tax Reducer</h2>
          <p className="page__subtitle">
            Find lawful ways to reduce your company's and business's tax liability.
          </p>
        </header>

        <div className="page__content">
          <Card
            title="Lawful tax planning, not tax evasion"
            testId="biz-reducer-intro"
          >
            <p className="taxreducer__intro-text">
              Business Tax Reducer reviews your company's or business's financial
              information, applicable tax rules, lawful deductions, exemptions,
              depreciation allowances, and sales tax input adjustments to identify
              legitimate tax-saving opportunities.
            </p>
            <p className="taxreducer__intro-text">
              This tool only supports legal tax optimization for your business — it
              will never suggest hiding income, fabricating expenses, falsifying
              records, or evading taxes. For general tax questions, keep using the
              AI Tax Assistant; Business Tax Reducer is specialized for structured
              analysis of your own business tax position.
            </p>
          </Card>

          <Card
            title="Your business tax information"
            subtitle="Fill in what you know — partial information is fine. The backend performs all analysis and calculations."
            testId="biz-reducer-form-card"
          >
            <form
              className="taxreducer-form"
              onSubmit={(e) => {
                e.preventDefault();
                void analyze();
              }}
              data-testid="biz-reducer-form"
            >
              <div className="grid grid--2">
                <Field
                  label="Tax Year"
                  helperText="e.g. 2024, 2025"
                  error={taxYearError ?? undefined}
                  data-testid="biz-reducer-tax-year"
                >
                  <input
                    type="number"
                    min={2020}
                    max={2030}
                    value={form.taxYear}
                    onChange={handleChange("taxYear")}
                    data-testid="biz-reducer-tax-year-input"
                  />
                </Field>

                <Field
                  label="Tax Type"
                  helperText="Which tax the analysis applies to"
                  data-testid="biz-reducer-tax-type"
                >
                  <select
                    value={form.taxType}
                    onChange={handleChange("taxType")}
                    data-testid="biz-reducer-tax-type-select"
                  >
                    {TAX_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </Field>

                <Field
                  label="Business Entity"
                  helperText="Company, AOP, or registered business"
                  data-testid="biz-reducer-taxpayer"
                >
                  <select
                    value={form.taxpayerType}
                    onChange={handleChange("taxpayerType")}
                    data-testid="biz-reducer-taxpayer-select"
                  >
                    {TAXPAYER_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </Field>

                <Field
                  label="Annual Turnover (PKR)"
                  helperText="Total business turnover for the tax year"
                  data-testid="biz-reducer-turnover"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.turnover}
                    onChange={handleChange("turnover")}
                    data-testid="biz-reducer-turnover-input"
                  />
                </Field>

                <Field
                  label="Tax Already Paid (PKR)"
                  helperText="Advance tax or withholding already deposited"
                  data-testid="biz-reducer-tax-paid"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.taxPaid}
                    onChange={handleChange("taxPaid")}
                    data-testid="biz-reducer-tax-paid-input"
                  />
                </Field>

                <Field
                  label="Allowable Business Expenses (PKR)"
                  helperText="Expenses your business can legally claim"
                  data-testid="biz-reducer-business-expenses"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.businessExpenses}
                    onChange={handleChange("businessExpenses")}
                    data-testid="biz-reducer-business-expenses-input"
                  />
                </Field>

                <Field
                  label="Depreciation Claimed (PKR)"
                  helperText="Depreciation on business fixed assets"
                  data-testid="biz-reducer-depreciation"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.depreciation}
                    onChange={handleChange("depreciation")}
                    data-testid="biz-reducer-depreciation-input"
                  />
                </Field>

                <Field
                  label="Capital Expenditure (PKR)"
                  helperText="New qualifying fixed asset purchases"
                  data-testid="biz-reducer-capital-expenditure"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.capitalExpenditure}
                    onChange={handleChange("capitalExpenditure")}
                    data-testid="biz-reducer-capital-expenditure-input"
                  />
                </Field>

                <Field
                  label="Sales Tax Input Paid (PKR)"
                  helperText="Input tax paid on business purchases"
                  data-testid="biz-reducer-input-tax-paid"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.inputTaxPaid}
                    onChange={handleChange("inputTaxPaid")}
                    data-testid="biz-reducer-input-tax-paid-input"
                  />
                </Field>

                <Field
                  label="Sales Tax Output Collected (PKR)"
                  helperText="Output tax collected on business sales"
                  data-testid="biz-reducer-output-tax-collected"
                  prefix="Rs"
                >
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    value={form.outputTaxCollected}
                    onChange={handleChange("outputTaxCollected")}
                    data-testid="biz-reducer-output-tax-collected-input"
                  />
                </Field>

                <Field
                  label="Applicable Deductions"
                  helperText="Deductions you believe apply (optional)"
                  data-testid="biz-reducer-deductions"
                >
                  <input
                    type="text"
                    value={form.deductions}
                    onChange={handleChange("deductions")}
                    placeholder="e.g. Zakat, research & development, Section 61 donations"
                    data-testid="biz-reducer-deductions-input"
                  />
                </Field>

                <Field
                  label="Applicable Exemptions"
                  helperText="Exemptions you believe apply (optional)"
                  data-testid="biz-reducer-exemptions"
                >
                  <input
                    type="text"
                    value={form.exemptions}
                    onChange={handleChange("exemptions")}
                    placeholder="e.g. initial allowance, industrial undertakings, SME rate"
                    data-testid="biz-reducer-exemptions-input"
                  />
                </Field>
              </div>

              <Field
                label="Other Relevant Business Information"
                helperText="Anything else that affects your business tax position"
                data-testid="biz-reducer-other-info"
              >
                <textarea
                  rows={3}
                  value={form.otherInfo}
                  onChange={handleChange("otherInfo")}
                  placeholder="e.g. registered manufacturer/retailer, branchless banking, export proceeds, input tax blocked due to non-filer status"
                  data-testid="biz-reducer-other-info-input"
                />
              </Field>

              <div className="form__actions">
                <Button
                  type="submit"
                  variant="primary"
                  loading={loading}
                  disabled={loading}
                  data-testid="biz-reducer-analyze-button"
                >
                  {loading
                    ? "Analyzing your business tax position…"
                    : "Analyze Business Tax Position"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={reset}
                  data-testid="biz-reducer-reset-button"
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
              description="Use the fields above to explore lawful deductions, exemptions, depreciation allowances, and input tax adjustments instead."
              action={
                <Button variant="ghost" onClick={() => setEvasionBlocked(false)}>
                  Dismiss
                </Button>
              }
              testId="biz-reducer-evasion-warning"
            />
          ) : null}

          {missingInfo ? (
            <StatusBanner
              kind="warn"
              title="More business information is required to estimate this accurately."
              description="Provide at least your turnover, expenses, depreciation, input tax, or notes about your business tax position, then run the analysis again."
              testId="biz-reducer-missing-info"
            />
          ) : null}

          {unavailable ? (
            <StatusBanner
              kind="err"
              title="Business tax analysis is temporarily unavailable. Please try again."
              testId="biz-reducer-error"
            />
          ) : null}

          {loading ? (
            <StatusBanner
              kind="info"
              title="Analyzing your business tax position…"
              description="The backend is reviewing applicable tax rules against the business information you provided."
              testId="biz-reducer-loading"
            />
          ) : null}

          {active && !loading ? (
            <div className="taxreducer-result" data-testid="biz-reducer-result">
              <Card
                title="Lawful tax-saving opportunities (estimated)"
                subtitle={`Scenario ${active.label} · based on the business information provided`}
                action={<Tag variant="accent">Estimate</Tag>}
                testId="biz-reducer-analysis-card"
              >
                <p
                  className="taxreducer__estimate-note"
                  data-testid="biz-reducer-estimate-note"
                >
                  Estimated figures are based on the business information provided
                  and are subject to eligibility. Savings are potential, not
                  guaranteed.
                </p>
                {isRefusal ? (
                  <StatusBanner
                    kind="info"
                    title="No additional lawful tax-saving opportunities were identified from the information provided."
                    description="Add more financial detail above and run the analysis again."
                    testId="biz-reducer-no-opportunities"
                  />
                ) : (
                  <div
                    className="taxreducer__analysis"
                    data-testid="biz-reducer-analysis"
                  >
                    {active.result.answer}
                  </div>
                )}
              </Card>

              <Card title="Analysis summary" testId="biz-reducer-summary-card">
                <Kv
                  rows={[
                    { key: "Tax year", value: active.form.taxYear },
                    {
                      key: "Business entity",
                      value: taxpayerLabel(active.form.taxpayerType),
                    },
                    {
                      key: "Tax type",
                      value: taxTypeLabel(active.form.taxType),
                    },
                    {
                      key: "Turnover provided",
                      value: active.form.turnover
                        ? formatPkr(Number(active.form.turnover))
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
                    {
                      key: "Verified",
                      value: (
                        <Tag
                          variant={
                            active.result.verification.passed ? "ok" : "err"
                          }
                        >
                          {active.result.verification.passed
                            ? "Verified"
                            : "Not verified"}
                        </Tag>
                      ),
                    },
                    {
                      key: "Grounded",
                      value: (
                        <Tag
                          variant={active.result.grounded ? "ok" : "warn"}
                        >
                          {active.result.grounded ? "Yes" : "No"}
                        </Tag>
                      ),
                    },
                  ]}
                  testId="biz-reducer-summary"
                />
              </Card>

              <Card
                title="Confidence & verification"
                testId="biz-reducer-verification-card"
              >
                <VerificationPanel
                  verification={active.result.verification}
                  grounded={active.result.grounded}
                  testId="biz-reducer-verification"
                />
              </Card>

              <Card
                title="Legal sources"
                testId="biz-reducer-sources-card"
              >
                {active.result.sources.length > 0 ? (
                  <SourceList
                    sources={active.result.sources}
                    testId="biz-reducer-sources"
                  />
                ) : (
                  <p className="muted" data-testid="biz-reducer-no-sources">
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
              testId="biz-reducer-scenarios"
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
                      data-testid={`biz-reducer-scenario-${s.label}`}
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
                              s.form.turnover
                                ? `turnover ${formatPkr(Number(s.form.turnover))}`
                                : "turnover not provided"
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
                                {s.result.verification.passed ? "Yes" : "No"}
                              </Tag>
                            ),
                          },
                        ]}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setActiveScenarioId(s.id)}
                        data-testid={`biz-reducer-scenario-view-${s.label}`}
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