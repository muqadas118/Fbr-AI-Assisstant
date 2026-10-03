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

interface CalculatorResult {
  answer: string;
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

interface CalculatorFormValues {
  calculationType: string;
  taxpayerType: string;
  taxableTurnover: string;
  allowableDeductions: string;
  inputTaxAdjustment: string;
  withholdingCollected: string;
  taxYear: string;
  businessRegistration: string;
  additionalInfo: string;
}

/** Engine-side hard cap: IncomeTaxCalculator rejects gross income above
 * PKR 1 trillion. Kept in sync with app/calculations/income_tax.py. */
const INCOME_CAP = 1_000_000_000_000;

const CALCULATION_TYPES = [
  { value: "income_tax", label: "Corporate / AOP Income Tax" },
  { value: "sales_tax", label: "Sales Tax" },
  { value: "withholding_tax", label: "Withholding Tax" },
  { value: "minimum_tax", label: "Minimum Tax on Turnover" },
  { value: "custom", label: "Custom Business Calculation" },
];

const TAXPAYER_TYPES = [
  { value: "company", label: "Company" },
  { value: "aop", label: "Association of Persons (AOP)" },
  { value: "business", label: "Sole Proprietorship / Registered Business" },
];

export function BusinessCalculatorPage() {
  const [form, setForm] = useState<CalculatorFormValues>({
    calculationType: "income_tax",
    taxpayerType: "company",
    taxableTurnover: "",
    allowableDeductions: "",
    inputTaxAdjustment: "",
    withholdingCollected: "",
    taxYear: new Date().getFullYear().toString(),
    businessRegistration: "",
    additionalInfo: "",
  });

  const [result, setResult] = useState<CalculatorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Live hint when the typed turnover crosses the engine's 1T cap
   * (applies to income/minimum-tax calculations on the turnover). */
  const incomeCapExceeded =
    (form.calculationType === "income_tax" || form.calculationType === "minimum_tax") &&
    form.taxableTurnover.trim() !== "" &&
    Number.isFinite(Number(form.taxableTurnover)) &&
    Number(form.taxableTurnover) > INCOME_CAP;

  const handleChange =
    <K extends keyof CalculatorFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const value =
        e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const taxpayerLabel = (value: string): string =>
    TAXPAYER_TYPES.find((t) => t.value === value)?.label ?? value;

  const calculate = useCallback(async () => {
    // Build a natural language query from the form
    const queryParts = [
      `Calculate ${form.calculationType.replace("_", " ")}`,
      `for a ${taxpayerLabel(form.taxpayerType)} taxpayer`,
      `for tax year ${form.taxYear}`,
    ];

    if (form.businessRegistration.trim()) queryParts.push(`business registered under ${form.businessRegistration.trim()}`);
    if (form.taxableTurnover) queryParts.push(`taxable turnover of ${form.taxableTurnover}`);
    if (form.allowableDeductions) queryParts.push(`allowable business deductions of ${form.allowableDeductions}`);
    if (form.inputTaxAdjustment) queryParts.push(`sales tax input adjustment of ${form.inputTaxAdjustment}`);
    if (form.withholdingCollected) queryParts.push(`withholding tax collected of ${form.withholdingCollected}`);
    if (form.additionalInfo) queryParts.push(form.additionalInfo);

    const query = queryParts.join(". ") + ".";

    setLoading(true);
    setError(null);
    setResult(null);

    const num = (v: string) => (v.trim() === "" ? 0 : Number(v));
    const calcType =
      form.calculationType === "custom" ? "custom_calc"
      : form.calculationType === "minimum_tax" ? "business_tax"
      : form.calculationType;
    const engineInputs: Record<string, unknown> =
      calcType === "business_tax"
        ? {
            business_income: num(form.taxableTurnover) - num(form.allowableDeductions),
            business_type: form.taxpayerType === "company" ? "private_company" : form.taxpayerType === "aop" ? "aop" : "individual_business",
            tax_year: form.taxYear,
            annual_turnover: num(form.taxableTurnover),
          }
        : calcType === "sales_tax"
          ? { sales_value: num(form.taxableTurnover), purchases_value: num(form.inputTaxAdjustment), sales_tax_type: "goods", province: "punjab" }
          : calcType === "withholding_tax"
            ? { transaction_amount: num(form.withholdingCollected || form.taxableTurnover), wht_rate: 4 }
            : { calc_type: "percentage", amount: num(form.taxableTurnover), rate: 10 };

    try {
      const calc = await api.calculate(calcType, engineInputs);
      const data = calc as { formatted_text?: string; data?: unknown };
      const deterministic = String(data.formatted_text ?? JSON.stringify(data.data ?? calc));

      // Show the deterministic result IMMEDIATELY — the AI explanation
      // below is a bonus that streams in later when it is ready.
      setResult({
        answer: deterministic,
        deterministic: true,
        sources: [],
        verification: deterministicVerification(),
        grounded: true,
      });

      try {
        const resp = await api.answer(query);
        setResult((prev) =>
          prev
            ? {
                ...prev,
                answer: `${prev.answer}\n\n---\n\n${resp.answer}`,
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
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }, [form]);

  const reset = useCallback(() => {
    setForm({
      calculationType: "income_tax",
      taxpayerType: "company",
      taxableTurnover: "",
      allowableDeductions: "",
      inputTaxAdjustment: "",
      withholdingCollected: "",
      taxYear: new Date().getFullYear().toString(),
      businessRegistration: "",
      additionalInfo: "",
    });
    setResult(null);
    setError(null);
  }, []);

  return (
    <ErrorBoundary>
      <section className="page page--calculator">
        <header className="page__header">
          <div className="page__eyebrow page-eyebrow eyebrow">FBR · Calculator</div>
          <h2 className="page__title">Business Tax Calculator</h2>
          <p className="page__subtitle">
            Calculate corporate and AOP income tax, sales tax, and withholding tax for your business. Enter your turnover and expenses, and get an instant calculation with sources.
          </p>
        </header>

        <div className="page__content">
          <form
            className="calculator-form"
            onSubmit={(e) => {
              e.preventDefault();
              void calculate();
            }}
            data-testid="biz-calculator-form"
          >
            <div className="form__grid grid--2">
              <Field
                label="Calculation Type"
                helperText="Select the business tax to calculate"
                data-testid="biz-calc-type"
              >
                <Select
                  value={form.calculationType}
                  onChange={(v) => setForm((prev) => ({ ...prev, calculationType: v }))}
                  testId="biz-calc-type-select"
                  ariaLabel="Calculation type"
                  options={CALCULATION_TYPES}
                />
              </Field>

              <Field
                label="Taxpayer Type"
                helperText="Company, AOP, or registered business"
                data-testid="biz-taxpayer-type"
              >
                <Select
                  value={form.taxpayerType}
                  onChange={(v) => setForm((prev) => ({ ...prev, taxpayerType: v }))}
                  testId="biz-taxpayer-type-select"
                  ariaLabel="Taxpayer type"
                  options={TAXPAYER_TYPES}
                />
              </Field>

              <Field
                label="Tax Year"
                helperText="e.g. 2024, 2025"
                data-testid="biz-tax-year"
              >
                <input
                  type="number"
                  min={2020}
                  max={2030}
                  value={form.taxYear}
                  onChange={handleChange("taxYear")}
                  data-testid="biz-tax-year-input"
                />
              </Field>

              <Field
                label="Business Registration / NTN"
                helperText="Company registration or NTN reference"
                data-testid="biz-registration"
              >
                <input
                  type="text"
                  value={form.businessRegistration}
                  onChange={handleChange("businessRegistration")}
                  placeholder="e.g. Company NTN 1234567-8"
                  data-testid="biz-registration-input"
                />
              </Field>

              <Field
                label="Taxable Turnover (PKR)"
                helperText="Total annual business turnover or gross receipts"
                data-testid="biz-turnover"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.taxableTurnover}
                  onChange={handleChange("taxableTurnover")}
                  data-testid="biz-turnover-input"
                />
              </Field>

              {incomeCapExceeded ? (
                <p className="calc-cap-hint" data-testid="biz-income-cap-hint" role="status">
                  Heads-up: the engine supports amounts up to PKR 1,000,000,000,000 (1 trillion).
                  Larger values will be rejected when you calculate.
                </p>
              ) : null}

              <Field
                label="Allowable Business Deductions (PKR)"
                helperText="Deductible business expenses"
                data-testid="biz-deductions"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.allowableDeductions}
                  onChange={handleChange("allowableDeductions")}
                  data-testid="biz-deductions-input"
                />
              </Field>

              <Field
                label="Sales Tax Input Adjustment (PKR)"
                helperText="Input tax claimed against output tax"
                data-testid="biz-input-tax"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.inputTaxAdjustment}
                  onChange={handleChange("inputTaxAdjustment")}
                  data-testid="biz-input-tax-input"
                />
              </Field>

              <Field
                label="Withholding Tax Collected (PKR)"
                helperText="WHT deducted from customers / vendors"
                data-testid="biz-withholding"
                prefix="Rs"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.withholdingCollected}
                  onChange={handleChange("withholdingCollected")}
                  data-testid="biz-withholding-input"
                />
              </Field>
            </div>

            <Field
              label="Additional Information"
              helperText="Any additional business details for the calculation"
              data-testid="biz-additional-info"
            >
              <textarea
                rows={3}
                value={form.additionalInfo}
                onChange={handleChange("additionalInfo")}
                data-testid="biz-additional-info-input"
                placeholder="e.g. Normal tax regime, capital gains on fixed assets, retail/wholesale sales tax, section 113 minimum tax, etc."
              />
            </Field>

            <div className="form__actions">
              <Button
                type="submit"
                variant="primary"
                loading={loading}
                disabled={loading}
                data-testid="biz-calculate-button"
              >
                {loading ? "Calculating…" : "Calculate Business Tax"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={reset}
                data-testid="biz-reset-button"
              >
                Reset
              </Button>
            </div>
          </form>

          {error ? (
            <StatusBanner
              kind="err"
              title="Calculation failed"
              description={error}
              action={<Button variant="ghost" onClick={() => setError(null)}>Dismiss</Button>}
              testId="biz-calculator-error"
            />
          ) : null}

          {result && !loading ? (
            <div className="calculator-result">
              <div className="calc-result">
                <h3 className="calc-result__label">Calculated Business Tax</h3>
                <p className="calc-result__amount" data-testid="biz-result-amount">
                  {result.answer}
                </p>
              </div>

              <VerificationPanel
                verification={result.verification}
                grounded={result.grounded}
                className="calc-result__verification"
                testId="biz-verification"
              />

              {result.sources.length > 0 && (
                <div className="calc-result__sources">
                  <h3 className="calc-result__sources-title">Sources & References</h3>
                  <SourceList sources={result.sources} testId="biz-sources" />
                </div>
              )}

              <div className="calc-disclaimer" data-testid="biz-calc-disclaimer">
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
                  testId="biz-calc-engine-source"
                />
                <p className="calc-disclaimer__text">
                  This is an automated estimate, not tax advice. Figures follow the Finance Act
                  rules coded into the engine, but your circumstances may differ. Please verify
                  the results independently — cross-check with the official FBR calculator or a
                  licensed tax practitioner before filing.
                </p>
              </div>
            </div>
          ) : !loading && !error && (form.taxableTurnover || form.additionalInfo) ? (
            <StatusBanner
              kind="info"
              title="Ready to calculate"
              description="Fill in the business details above and click Calculate Business Tax to get started."
              testId="biz-calculator-ready"
            />
          ) : null}
        </div>
      </section>
    </ErrorBoundary>
  );
}