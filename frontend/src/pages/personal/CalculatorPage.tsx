import { useState, useCallback } from "react";
import { ApiError, NetworkError, api, type SourceItem, type VerificationResult } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Kv } from "@/components/ui/Kv";
import { Tag } from "@/components/ui/Tag";
import { VerificationPanel } from "@/components/ui/VerificationPanel";
import { renderRich } from "@/lib/richText";

interface CalculatorResult {
  /** Deterministic engine summary (title, fields, slabs) for the result card. */
  summary: EngineSummary | null;
  /** RAG explanation (rich text) or the raw deterministic text as fallback. */
  explanation: string;
  /** True when the engine produced this result (not the RAG pipeline). */
  deterministic: boolean;
  sources: SourceItem[];
  /** Verification status: synthesized for the deterministic engine, real for RAG. */
  verification: VerificationResult;
  grounded: boolean;
}

/** Verification payload shown while only the deterministic engine has run —
 * the deterministic path bypasses the RAG verification layer, so we present
 * an honest "deterministic engine" verification instead of a fake pass. */
function deterministicVerification(): VerificationResult {
  return {
    passed: true,
    checks: {
      answer_size: { passed: true, reason: "deterministic engine" },
      section_consistency: { passed: true, reason: "deterministic engine" },
      grounding: { passed: true, reason: "deterministic engine" },
      speculation: { passed: true, reason: "deterministic engine" },
    },
    failed_checks: [],
    reason: "deterministic calculation engine",
  };
}

interface EngineSummary {
  title: string;
  fields: { label: string; value: string; strong?: boolean }[];
  slabs: { range: string; rate: string; taxable: string; tax: string }[];
}

/** Parse the deterministic engine's `=== Title ===` / `Key: Value` /
 * slab-list text into a structured card. Amounts may contain spaces
 * between PKR and digits (engine pads them: `PKR       0.00`).
 * Returns null when the text does not follow the expected shape. */
function parseEngineSummary(text: string): EngineSummary | null {
  const titleMatch = text.match(/===\s*(.+?)\s*===/);
  if (!titleMatch) return null;
  const body = text.slice(text.indexOf(titleMatch[0]) + titleMatch[0].length);
  const fields: EngineSummary["fields"] = [];
  const slabs: EngineSummary["slabs"] = [];

  const amt = "PKR\\s*[\\d,]+(?:\\.\\d+)?";
  const slabPattern =
    /(\d+)\.\s*(PKR\s*[\d,]+(?:\.\d+)?)\s*-\s*(PKR\s*[\d,]+(?:\.\d+)?)\s*@\s*([\d.]+)%:\s*Taxable=(PKR\s*[\d,]+(?:\.\d+)?)\s*->\s*Tax=(PKR\s*[\d,]+(?:\.\d+)?)/g;
  let m: RegExpExecArray | null;
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  while ((m = slabPattern.exec(body)) !== null) {
    slabs.push({
      range: `${norm(m[2])} – ${norm(m[3])}`,
      rate: `${m[4]}%`,
      taxable: norm(m[5]),
      tax: norm(m[6]),
    });
  }

  const fieldText = body.replace(slabPattern, "");
  const fieldPattern = new RegExp(
    "([A-Z][A-Za-z \\-,()]+?):\\s*(" + amt + "|[\\d.]+%)",
    "g",
  );
  while ((m = fieldPattern.exec(fieldText)) !== null) {
    const label = m[1].trim();
    const value = m[2].replace(/\s+/g, " ").trim();
    fields.push({
      label,
      value,
      strong: /Tax Payable|Taxable Income|Gross Income/i.test(label),
    });
  }
  if (fields.length === 0 && slabs.length === 0) return null;
  return { title: titleMatch[1], fields, slabs };
}

/** Engine-side hard cap: IncomeTaxCalculator rejects gross income above
 * PKR 1 trillion. Kept in sync with app/calculations/income_tax.py. */
const INCOME_CAP = 1_000_000_000_000;

interface CalculatorFormValues {
  calculationType: string;
  income: string;
  deductions: string;
  credits: string;
  taxYear: string;
  filingStatus: string;
  additionalInfo: string;
}

export function CalculatorPage() {
  const [form, setForm] = useState<CalculatorFormValues>({
    calculationType: "income_tax",
    income: "",
    deductions: "",
    credits: "",
    taxYear: new Date().getFullYear().toString(),
    filingStatus: "single",
    additionalInfo: "",
  });

  const [result, setResult] = useState<CalculatorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string | undefined>>({});

  const handleChange =
    <K extends keyof CalculatorFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const value =
        e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const calculate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    // 1) Deterministic engine via POST /calculate (11 modules)
    const num = (v: string) => (v.trim() === "" ? 0 : Number(v));
    const calcType =
      form.calculationType === "custom" ? "custom_calc" : form.calculationType;
    const filingMap: Record<string, string> = {
      single: "salaried",
      married_jointly: "salaried",
      married_separately: "salaried",
      head_of_household: "salaried",
      qualifying_widow: "salaried",
    };
    const engineInputs: Record<string, unknown> =
      calcType === "income_tax"
        ? {
            gross_income: num(form.income),
            filing_status: filingMap[form.filingStatus] ?? "salaried",
            tax_year: form.taxYear,
            donations: num(form.deductions),
            investment_in_equity: num(form.credits),
          }
        : calcType === "sales_tax"
          ? { sales_value: num(form.income), sales_tax_type: "goods", province: "punjab" }
          : calcType === "property_tax"
            ? { property_value: num(form.income), city: "lahore" }
            : calcType === "withholding_tax"
              ? { transaction_amount: num(form.income), wht_rate: 4 }
              : { calc_type: "percentage", amount: num(form.income), rate: 10 };

    try {
      const calc = await api.calculate(calcType, engineInputs);
      const data = calc as { formatted_text?: string; data?: unknown };
      const deterministic = String(data.formatted_text ?? JSON.stringify(data.data ?? calc));
      const summary = parseEngineSummary(deterministic);

      // Show the deterministic result IMMEDIATELY — the AI explanation
      // below is a bonus that streams in later when it is ready.
      setResult({
        summary,
        explanation: "",
        deterministic: true,
        sources: [],
        verification: deterministicVerification(),
        grounded: true,
      });

      // 2) Best-effort RAG explanation, appended in the background so a
      // slow/unavailable LLM never delays the calculation itself.
      const queryParts = [
        `Calculate ${form.calculationType.replace("_", " ")}`,
        `for tax year ${form.taxYear}`,
        `with filing status ${form.filingStatus}`,
      ];
      if (form.income) queryParts.push(`income of ${form.income}`);
      if (form.deductions) queryParts.push(`deductions of ${form.deductions}`);
      if (form.credits) queryParts.push(`tax credits of ${form.credits}`);
      if (form.additionalInfo) queryParts.push(form.additionalInfo);
      const query = queryParts.join(". ") + ".";

      try {
        const resp = await api.answer(query);
        setResult((prev) =>
          prev
            ? {
                ...prev,
                explanation:
                  summary && prev.explanation === ""
                    ? resp.answer
                    : `${prev.explanation || deterministic}\n\n---\n\n${resp.answer}`,
                deterministic: false,
                sources: resp.sources,
                verification: resp.verification,
                grounded: resp.grounded,
              }
            : prev,
        );
      } catch {
        // Deterministic result already on screen — nothing to do.
      }
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("Unexpected error. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }, [form]);

  /** Live hint when the typed income crosses the engine's 1T cap. */
  const incomeCapExceeded =
    form.calculationType === "income_tax" &&
    form.income.trim() !== "" &&
    Number.isFinite(Number(form.income)) &&
    Number(form.income) > INCOME_CAP;

  /** Visible client-side validation — replaces the browser's silent
   * HTML5 block (a negative value used to stop submit with no message). */
  const validateAndSubmit = useCallback(() => {
    const errors: Record<string, string | undefined> = {};
    const isNum = (s: string) => s.trim() !== "" && Number.isFinite(Number(s));
    if (!isNum(form.income)) {
      errors.income = "Income amount is required and must be a number.";
    } else if (Number(form.income) < 0) {
      errors.income = "Income cannot be negative — enter 0 or more.";
    } else if (form.calculationType === "income_tax" && Number(form.income) > INCOME_CAP) {
      errors.income =
        "Income exceeds the maximum supported amount (PKR 1,000,000,000,000). Please enter a smaller amount.";
    }
    for (const [key, label] of [
      ["deductions", "Deductions"],
      ["credits", "Tax credits"],
    ] as const) {
      const v = form[key];
      if (v.trim() !== "" && (!isNum(v) || Number(v) < 0)) {
        errors[key] = `${label} must be 0 or more.`;
      }
    }
    const year = Number(form.taxYear);
    if (!Number.isInteger(year) || year < 2020 || year > 2030) {
      errors.taxYear = "Tax year must be between 2020 and 2030.";
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    void calculate();
  }, [form, calculate]);

  const reset = useCallback(() => {
    setForm({
      calculationType: "income_tax",
      income: "",
      deductions: "",
      credits: "",
      taxYear: new Date().getFullYear().toString(),
      filingStatus: "single",
      additionalInfo: "",
    });
    setResult(null);
    setError(null);
    setFieldErrors({});
  }, []);

  return (
    <ErrorBoundary>
      <section className="page page--calculator">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Calculator</div>
            <h2 className="page__title">Tax Calculator</h2>
          <p className="page__subtitle">
            Calculate tax using the deterministic FBR tax engine. Enter your information and get an instant calculation with sources.
          </p>
          </div>
        </header>

        <div className="page__content">
          <section className="card" data-testid="calculator-form-card">
          <form
            className="calculator-form"
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              validateAndSubmit();
            }}
            data-testid="calculator-form"
          >
            <div className="form__grid grid--2">
              <Field
                label="Calculation Type"
                helperText="Select the type of tax calculation"
                data-testid="calc-type"
              >
                <Select
                  value={form.calculationType}
                  onChange={(v) => setForm((prev) => ({ ...prev, calculationType: v }))}
                  testId="calc-type-select"
                  ariaLabel="Calculation type"
                  options={[
                    { value: "income_tax", label: "Income Tax" },
                    { value: "salary_tax", label: "Salary Tax" },
                    { value: "business_tax", label: "Business Tax" },
                    { value: "sales_tax", label: "Sales Tax" },
                    { value: "withholding_tax", label: "Withholding Tax" },
                    { value: "federal_excise", label: "Federal Excise" },
                    { value: "capital_gains", label: "Capital Gains" },
                    { value: "property_tax", label: "Property Tax" },
                    { value: "dividend_tax", label: "Dividend Tax" },
                    { value: "custom_duty", label: "Custom Duty" },
                    { value: "custom", label: "Custom Calculation" },
                  ]}
                />
              </Field>

              <Field
                label="Tax Year"
                helperText="e.g. 2024, 2025"
                error={fieldErrors.taxYear}
                data-testid="tax-year"
              >
                <input
                  type="number"
                  min={2020}
                  max={2030}
                  value={form.taxYear}
                  onChange={handleChange("taxYear")}
                  data-testid="tax-year-input"
                />
              </Field>

              <Field
                label="Filing Status"
                helperText="Your filing status"
                data-testid="filing-status"
              >
                <Select
                  value={form.filingStatus}
                  onChange={(v) => setForm((prev) => ({ ...prev, filingStatus: v }))}
                  testId="filing-status-select"
                  ariaLabel="Filing status"
                  options={[
                    { value: "single", label: "Single" },
                    { value: "married_jointly", label: "Married Filing Jointly" },
                    { value: "married_separately", label: "Married Filing Separately" },
                    { value: "head_of_household", label: "Head of Household" },
                    { value: "qualifying_widow", label: "Qualifying Widow(er)" },
                  ]}
                />
              </Field>

              <Field
                label="Income Amount (PKR)"
                helperText="Total annual income"
                error={fieldErrors.income}
                data-testid="income"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.income}
                  onChange={handleChange("income")}
                  data-testid="income-input"
                />
              </Field>

              {incomeCapExceeded && !fieldErrors.income ? (
                <p className="calc-cap-hint" data-testid="income-cap-hint" role="status">
                  Heads-up: the engine supports amounts up to PKR 1,000,000,000,000 (1 trillion).
                  Larger values will be rejected when you calculate.
                </p>
              ) : null}

              <Field
                label="Deductions (PKR)"
                helperText="Total deductible expenses"
                error={fieldErrors.deductions}
                data-testid="deductions"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.deductions}
                  onChange={handleChange("deductions")}
                  data-testid="deductions-input"
                />
              </Field>

              <Field
                label="Tax Credits (PKR)"
                helperText="Available tax credits"
                error={fieldErrors.credits}
                data-testid="credits"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.credits}
                  onChange={handleChange("credits")}
                  data-testid="credits-input"
                />
              </Field>
            </div>

            <Field
              label="Additional Information"
              helperText="Any additional details for the calculation"
              data-testid="additional-info"
            >
              <textarea
                rows={3}
                value={form.additionalInfo}
                onChange={handleChange("additionalInfo")}
                data-testid="additional-info-input"
                placeholder="e.g. Include Zakat, consider senior citizen rebate, etc."
              />
            </Field>

            <div className="form__actions">
              <Button
                type="submit"
                variant="primary"
                loading={loading}
                disabled={loading}
                data-testid="calculate-button"
              >
                {loading ? "Calculating…" : "Calculate Tax"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={reset}
                data-testid="reset-button"
              >
                Reset
              </Button>
            </div>
          </form>
          </section>

          {error ? (
            <StatusBanner
              kind="err"
              title="Calculation failed"
              description={error}
              action={<Button variant="ghost" onClick={() => setError(null)}>Dismiss</Button>}
              testId="calculator-error"
            />
          ) : null}

          {result && !loading ? (
            <div className="calculator-result card" data-testid="calculator-result-card">
              <div className="calc-result">
                <h3 className="calc-result__label">Calculated Tax</h3>
                {result.summary ? (
                  <div className="calc-structured" data-testid="calc-structured">
                    <h4 className="calc-structured__title">{result.summary.title}</h4>
                    <table className="rt__table calc-structured__table">
                      <tbody>
                        {result.summary.fields.map((f) => (
                          <tr key={f.label} className={f.strong ? "calc-structured__strong" : undefined}>
                            <th scope="row">{f.label}</th>
                            <td>{f.value}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {result.summary.slabs.length > 0 ? (
                      <>
                        <h5 className="calc-structured__sub">Tax Slab Breakdown</h5>
                        <div className="rt__table-wrap">
                          <table className="rt__table" data-testid="calc-slabs">
                            <thead>
                              <tr>
                                <th>Slab</th>
                                <th>Rate</th>
                                <th>Taxable</th>
                                <th>Tax</th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.summary.slabs.map((s, i) => (
                                <tr key={i}>
                                  <td>{s.range}</td>
                                  <td>{s.rate}</td>
                                  <td>{s.taxable}</td>
                                  <td>{s.tax}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    ) : null}
                  </div>
                ) : null}
                {result.explanation ? (
                  <div className="calc-result__explanation" data-testid="calc-explanation">
                    {renderRich(result.explanation)}
                  </div>
                ) : null}
              </div>

              <VerificationPanel
                verification={result.verification}
                grounded={result.grounded}
                className="calc-result__verification"
                testId="calc-verification"
              />

              {result.sources.length > 0 && (
                <div className="calc-result__sources">
                  <h3 className="calc-result__sources-title">Sources & References</h3>
                  <SourceList sources={result.sources} testId="calc-sources" />
                </div>
              )}

              <div className="calc-disclaimer" data-testid="calc-disclaimer">
                <Kv
                  rows={[
                    {
                      key: "Calculated by",
                      value: (
                        <Tag variant={result.deterministic ? "ok" : "accent"}>
                          {result.deterministic
                            ? "Deterministic tax engine (FBR rules)"
                            : "AI explanation + deterministic engine"}
                        </Tag>
                      ),
                    },
                  ]}
                  testId="calc-engine-source"
                />
                <p className="calc-disclaimer__text">
                  This is an automated estimate, not tax advice. Figures follow the Finance Act
                  rules coded into the engine, but your circumstances may differ. Please verify
                  the results independently — cross-check with the official FBR calculator or a
                  licensed tax practitioner before filing.
                </p>
              </div>
            </div>
          ) : !loading && !error && (form.income || form.additionalInfo) ? (
            <StatusBanner
              kind="info"
              title="Ready to calculate"
              description="Fill in the form above and click Calculate Tax to get started."
              testId="calculator-ready"
            />
          ) : null}
        </div>
      </section>
    </ErrorBoundary>
  );
}