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

  const handleChange =
    <K extends keyof CalculatorFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const value =
        e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const calculate = useCallback(async () => {
    // Build a natural language query from the form
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

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const resp = await api.answer(query);
      setResult({
        answer: resp.answer,
        verification: resp.verification,
        grounded: resp.grounded,
        sources: resp.sources,
      });
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
  }, []);

  return (
    <ErrorBoundary>
      <section className="page page--calculator">
        <header className="page__header">
          <h2 className="page__title">Tax Calculator</h2>
          <p className="page__subtitle">
            Calculate tax using the verified backend pipeline. Enter your information and get a calculation with sources and verification.
          </p>
        </header>

        <div className="page__content">
          <form
            className="calculator-form"
            onSubmit={(e) => {
              e.preventDefault();
              void calculate();
            }}
            data-testid="calculator-form"
          >
            <div className="form__grid grid--2">
              <Field
                label="Calculation Type"
                helperText="Select the type of tax calculation"
                data-testid="calc-type"
              >
                <select
                  value={form.calculationType}
                  onChange={handleChange("calculationType")}
                  data-testid="calc-type-select"
                >
                  <option value="income_tax">Income Tax</option>
                  <option value="sales_tax">Sales Tax</option>
                  <option value="property_tax">Property Tax</option>
                  <option value="withholding_tax">Withholding Tax</option>
                  <option value="custom">Custom Calculation</option>
                </select>
              </Field>

              <Field
                label="Tax Year"
                helperText="e.g. 2024, 2025"
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
                <select
                  value={form.filingStatus}
                  onChange={handleChange("filingStatus")}
                  data-testid="filing-status-select"
                >
                  <option value="single">Single</option>
                  <option value="married_jointly">Married Filing Jointly</option>
                  <option value="married_separately">Married Filing Separately</option>
                  <option value="head_of_household">Head of Household</option>
                  <option value="qualifying_widow">Qualifying Widow(er)</option>
                </select>
              </Field>

              <Field
                label="Income Amount (PKR)"
                helperText="Total annual income"
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

              <Field
                label="Deductions (PKR)"
                helperText="Total deductible expenses"
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
            <div className="calculator-result">
              <div className="calc-result">
                <h3 className="calc-result__label">Calculated Tax</h3>
                <p className="calc-result__amount" data-testid="calc-result-amount">
                  {result.answer}
                </p>
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