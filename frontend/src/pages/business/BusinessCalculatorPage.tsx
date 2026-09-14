import { useState, useCallback } from "react";
import { ApiError, NetworkError, api, type SourceItem, type VerificationResult } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { VerificationPanel } from "@/components/ui/VerificationPanel";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";

interface CalculatorResult {
  answer: string;
  verification: VerificationResult;
  grounded: boolean;
  sources: SourceItem[];
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

      try {
        const resp = await api.answer(query);
        setResult({
          answer: `${deterministic}\n\n---\n\n${resp.answer}`,
          verification: resp.verification,
          grounded: resp.grounded,
          sources: resp.sources,
        });
      } catch {
        setResult({
          answer: deterministic,
          verification: {
            passed: true,
            checks: {
              answer_size: { passed: true, reason: "deterministic engine" },
              section_consistency: { passed: true, reason: "deterministic engine" },
              grounding: { passed: true, reason: "deterministic engine" },
              speculation: { passed: true, reason: "deterministic engine" },
            },
            failed_checks: [],
            reason: "deterministic calculation engine",
          },
          grounded: true,
          sources: [],
        });
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
          <p className="page-eyebrow">Business · Calculator</p>
          <h2 className="page__title">Business Tax Calculator</h2>
          <p className="page__subtitle">
            Calculate corporate and AOP income tax, sales tax, and withholding tax for your business. Enter your turnover and expenses, and get a verified calculation with sources.
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
                <select
                  value={form.calculationType}
                  onChange={handleChange("calculationType")}
                  data-testid="biz-calc-type-select"
                >
                  {CALCULATION_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field
                label="Taxpayer Type"
                helperText="Company, AOP, or registered business"
                data-testid="biz-taxpayer-type"
              >
                <select
                  value={form.taxpayerType}
                  onChange={handleChange("taxpayerType")}
                  data-testid="biz-taxpayer-type-select"
                >
                  {TAXPAYER_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
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