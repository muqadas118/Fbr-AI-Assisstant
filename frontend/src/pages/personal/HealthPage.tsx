import { useState, useCallback } from "react";
import clsx from "clsx";
import {
  api,
  ApiError,
  NetworkError,
  type TaxHealthResponse,
  type RiskAnalysisResponse,
  type HealthIssue,
  type HealthRecommendation,
  type RiskFactor,
} from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Loading } from "@/components/shell/Loading";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = "health" | "risks" | "penalties";

interface HealthFormValues {
  ntn: string;
  taxYear: string;
  itrFiled: boolean;
  declaredIncome: string;
  taxAssessed: string;
  taxPaid: string;
  whtCollected: string;
  whtDeposited: string;
  stCollected: string;
  stDeposited: string;
  noticesOutstanding: string;
}

interface RiskFormValues {
  taxOutstanding: string;
  noticesCount: string;
  itrFiled: boolean;
  whtShortfall: string;
  stShortfall: string;
  estimatedIncome: string;
  declaredIncome: string;
}

interface PenaltyFormValues {
  taxAssessed: string;
  taxPaid: string;
  daysLateItr: string;
  daysLatePayment: string;
  whtShortfall: string;
  stShortfall: string;
  isConcealment: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function emptyHealthForm(): HealthFormValues {
  return {
    ntn: "",
    taxYear: new Date().getFullYear().toString(),
    itrFiled: false,
    declaredIncome: "",
    taxAssessed: "",
    taxPaid: "",
    whtCollected: "",
    whtDeposited: "",
    stCollected: "",
    stDeposited: "",
    noticesOutstanding: "",
  };
}

function emptyRiskForm(): RiskFormValues {
  return {
    taxOutstanding: "",
    noticesCount: "",
    itrFiled: false,
    whtShortfall: "",
    stShortfall: "",
    estimatedIncome: "",
    declaredIncome: "",
  };
}

function emptyPenaltyForm(): PenaltyFormValues {
  return {
    taxAssessed: "",
    taxPaid: "",
    daysLateItr: "",
    daysLatePayment: "",
    whtShortfall: "",
    stShortfall: "",
    isConcealment: false,
  };
}

function formatPkr(value: number | undefined | null): string {
  if (value == null) return "—";
  return `PKR ${value.toLocaleString("en-US")}`;
}

function severityVariant(severity: string): "err" | "warn" | "accent" | "default" {
  const s = severity.toLowerCase();
  if (s === "critical" || s === "high") return "err";
  if (s === "medium") return "warn";
  if (s === "low") return "accent";
  return "default";
}

function riskLevelVariant(level: string): "err" | "warn" | "accent" | "ok" {
  const l = level.toLowerCase();
  if (l === "high" || l === "critical") return "err";
  if (l === "medium") return "warn";
  if (l === "low") return "ok";
  return "accent";
}

function healthGradeColor(grade: string): string {
  const g = grade.toUpperCase();
  if (g === "A+" || g === "A") return "var(--c-ok)";
  if (g === "B") return "var(--c-info)";
  if (g === "C") return "var(--c-warn)";
  return "var(--c-err)";
}

function scoreColor(score: number): string {
  if (score >= 80) return "var(--c-ok)";
  if (score >= 60) return "var(--c-info)";
  if (score >= 40) return "var(--c-warn)";
  return "var(--c-err)";
}

function ProgressBar({ value, label }: { value: number; label: string }) {
  const color = scoreColor(value);
  return (
    <div className="health-progress">
      <div className="health-progress__meta">
        <span className="health-progress__label">{label}</span>
        <span className="health-progress__value" style={{ color }}>{value}/100</span>
      </div>
      <div className="health-progress__track" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className="health-progress__fill" style={{ width: `${value}%`, background: color }} />
      </div>
    </div>
  );
}

function IssueRow({ issue }: { issue: HealthIssue }) {
  return (
    <div className="health-issue">
      <div className="health-issue__header">
        <Tag variant={severityVariant(issue.severity)}>{issue.severity}</Tag>
        <span className="health-issue__title">{issue.title}</span>
      </div>
      <p className="health-issue__desc">{issue.description}</p>
      <div className="health-issue__footer">
        <span className="health-issue__impact">Tax impact: {formatPkr(issue.tax_impact)}</span>
        <span className="health-issue__penalty">Penalty est: {formatPkr(issue.penalty_estimate)}</span>
      </div>
    </div>
  );
}

function RecommendationRow({ rec, index }: { rec: HealthRecommendation; index: number }) {
  const priorityVariant = rec.priority === "critical" || rec.priority === "high"
    ? "err"
    : rec.priority === "medium" ? "warn" : "accent";
  return (
    <div className="health-rec">
      <div className="health-rec__header">
        <span className="health-rec__num">{index + 1}</span>
        <Tag variant={priorityVariant}>{rec.priority}</Tag>
        <span className="health-rec__action">{rec.action}</span>
      </div>
      <p className="health-rec__reason">{rec.reason}</p>
      {rec.deadline ? (
        <p className="health-rec__deadline">Deadline: <strong>{rec.deadline}</strong></p>
      ) : null}
    </div>
  );
}

function RiskFactorRow({ factor }: { factor: RiskFactor }) {
  const variant = riskLevelVariant(factor.level);
  const weightPct = Math.round((factor.weight || 0) * 100);
  return (
    <div className="risk-factor">
      <div className="risk-factor__header">
        <Tag variant={variant}>{factor.level}</Tag>
        <span className="risk-factor__desc">{factor.description}</span>
      </div>
      <div className="health-progress__track health-progress__track--sm" role="progressbar" aria-valuenow={weightPct} aria-valuemin={0} aria-valuemax={100}>
        <div className="health-progress__fill" style={{ width: `${weightPct}%`, background: `var(--c-${variant === "err" ? "err" : variant === "warn" ? "warn" : variant === "ok" ? "ok" : "accent"})` }} />
      </div>
      {factor.mitigation ? (
        <p className="risk-factor__mitigation">
          <span className="eyebrow">Mitigation</span> {factor.mitigation}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Health Check Tab
// ---------------------------------------------------------------------------

function HealthCheckTab() {
  const [form, setForm] = useState<HealthFormValues>(emptyHealthForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TaxHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const { show: notify } = useNotification();

  const handleChange = <K extends keyof HealthFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
      setErrors((prev) => { const n = { ...prev }; delete n[field]; return n; });
    };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!form.ntn.trim()) errs.ntn = "NTN is required";
    if (!form.taxYear.trim()) errs.taxYear = "Tax year is required";
    const yr = Number(form.taxYear);
    if (isNaN(yr) || yr < 2000 || yr > 2100) errs.taxYear = "Enter a valid tax year";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const submit = useCallback(async () => {
    if (!validate()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await api.taxHealth.check({
        ntn: form.ntn.trim(),
        tax_year: Number(form.taxYear),
        itr_filed: form.itrFiled,
        declared_income: form.declaredIncome ? Number(form.declaredIncome) : undefined,
        tax_assessed: form.taxAssessed ? Number(form.taxAssessed) : undefined,
        tax_paid: form.taxPaid ? Number(form.taxPaid) : undefined,
        wht_collected: form.whtCollected ? Number(form.whtCollected) : undefined,
        wht_deposited: form.whtDeposited ? Number(form.whtDeposited) : undefined,
        st_collected: form.stCollected ? Number(form.stCollected) : undefined,
        st_deposited: form.stDeposited ? Number(form.stDeposited) : undefined,
        notices_outstanding: form.noticesOutstanding ? Number(form.noticesOutstanding) : undefined,
      });
      setResult(resp);
      notify("ok", "Tax health check completed successfully.");
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }, [form, notify]);

  return (
    <div className="health-tab">
      <Card title="Enter Tax Information" subtitle="Fill in your tax data for a comprehensive health check" testId="health-form-card">
        <form
          className="health-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="health-form"
        >
          <div className="grid grid--2">
            <Field label="NTN" error={errors.ntn} data-testid="health-ntn">
              <input
                type="text"
                value={form.ntn}
                onChange={handleChange("ntn")}
                placeholder="e.g. 1234567-9"
                data-testid="health-ntn-input"
              />
            </Field>
            <Field label="Tax Year" error={errors.taxYear} data-testid="health-tax-year">
              <input
                type="number"
                min={2000}
                max={2100}
                value={form.taxYear}
                onChange={handleChange("taxYear")}
                data-testid="health-tax-year-input"
              />
            </Field>
          </div>

          <Field label="ITR Filed" data-testid="health-itr-filed" className="field--checkbox-row">
            <label className="field__checkbox-label">
              <input
                type="checkbox"
                checked={form.itrFiled}
                onChange={handleChange("itrFiled")}
                data-testid="health-itr-filed-input"
              />
              Income Tax Return (ITR) has been filed
            </label>
          </Field>

          <div className="grid grid--2">
            <Field label="Declared Income (PKR)" data-testid="health-declared-income" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.declaredIncome} onChange={handleChange("declaredIncome")} data-testid="health-declared-income-input" />
            </Field>
            <Field label="Tax Assessed (PKR)" data-testid="health-tax-assessed" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.taxAssessed} onChange={handleChange("taxAssessed")} data-testid="health-tax-assessed-input" />
            </Field>
            <Field label="Tax Paid (PKR)" data-testid="health-tax-paid" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.taxPaid} onChange={handleChange("taxPaid")} data-testid="health-tax-paid-input" />
            </Field>
          </div>

          <div className="health-section-label">
            <span className="eyebrow">Withholding Tax (WHT)</span>
          </div>
          <div className="grid grid--2">
            <Field label="WHT Collected (PKR)" data-testid="health-wht-collected" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.whtCollected} onChange={handleChange("whtCollected")} data-testid="health-wht-collected-input" />
            </Field>
            <Field label="WHT Deposited (PKR)" data-testid="health-wht-deposited" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.whtDeposited} onChange={handleChange("whtDeposited")} data-testid="health-wht-deposited-input" />
            </Field>
          </div>

          <div className="health-section-label">
            <span className="eyebrow">Sales Tax</span>
          </div>
          <div className="grid grid--2">
            <Field label="ST Collected (PKR)" data-testid="health-st-collected" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.stCollected} onChange={handleChange("stCollected")} data-testid="health-st-collected-input" />
            </Field>
            <Field label="ST Deposited (PKR)" data-testid="health-st-deposited" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.stDeposited} onChange={handleChange("stDeposited")} data-testid="health-st-deposited-input" />
            </Field>
          </div>

          <Field label="Notices Outstanding" data-testid="health-notices">
            <input type="number" min={0} value={form.noticesOutstanding} onChange={handleChange("noticesOutstanding")} data-testid="health-notices-input" />
          </Field>

          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="health-submit">
              {loading ? "Checking health…" : "Run Health Check"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setForm(emptyHealthForm()); setResult(null); setError(null); setErrors({}); }} data-testid="health-reset">
              Reset
            </Button>
          </div>
        </form>
      </Card>

      {loading ? (
        <div className="health-loading">
          <Loading label="Analyzing your tax health…" testId="health-loading" />
        </div>
      ) : null}

      {error ? (
        <StatusBanner kind="err" title="Health check failed" description={error} testId="health-error" />
      ) : null}

      {result && !loading ? (
        <div className="health-result" data-testid="health-result">
          {/* Score Hero */}
          <Card testId="health-score-card">
            <div className="health-score-hero">
              <div className="health-score-hero__grade" style={{ color: healthGradeColor(result.health_grade) }}>
                {result.health_grade}
              </div>
              <div className="health-score-hero__info">
                <div className="health-score-hero__score">
                  <span className="health-score-hero__score-value" style={{ color: scoreColor(result.health_score) }}>
                    {result.health_score}
                  </span>
                  <span className="health-score-hero__score-max">/100</span>
                </div>
                <div className="health-score-hero__meta">
                  <Tag variant={result.risk_level === "low" ? "ok" : result.risk_level === "medium" ? "warn" : "err"}>
                    {result.risk_level} risk
                  </Tag>
                  {result.itr_filed ? (
                    <Tag variant="ok">ITR Filed</Tag>
                  ) : (
                    <Tag variant="err">ITR Not Filed</Tag>
                  )}
                  {result.critical_issues_count > 0 ? (
                    <Tag variant="err">{result.critical_issues_count} critical issue{result.critical_issues_count !== 1 ? "s" : ""}</Tag>
                  ) : null}
                </div>
              </div>
            </div>
          </Card>

          {/* Score Breakdown */}
          <Card title="Score Breakdown" testId="health-breakdown-card">
            <div className="health-breakdown">
              <ProgressBar value={result.filing_score} label="Filing Score" />
              <ProgressBar value={result.deposit_score} label="Deposit Score" />
              <ProgressBar value={result.compliance_score} label="Compliance Score" />
              <ProgressBar value={result.reconciliation_score} label="Reconciliation Score" />
            </div>
          </Card>

          {/* Tax Summary */}
          <Card title="Tax Summary" testId="health-summary-card">
            <Kv
              rows={[
                { key: "NTN", value: result.ntn },
                { key: "Tax Year", value: result.tax_year },
                { key: "Declared Income", value: formatPkr(result.declared_income) },
                { key: "Estimated Income", value: formatPkr(result.estimated_income) },
                { key: "Tax Assessed", value: formatPkr(result.tax_assessed) },
                { key: "Tax Paid", value: formatPkr(result.tax_paid) },
                { key: "Tax Outstanding", value: formatPkr(result.tax_outstanding) },
                { key: "WHT Shortfall", value: formatPkr(result.wht_shortfall) },
                { key: "ST Shortfall", value: formatPkr(result.st_shortfall) },
                { key: "Total Penalty Exposure", value: <strong style={{ color: result.total_penalty_exposure > 0 ? "var(--c-err)" : "var(--c-ok)" }}>{formatPkr(result.total_penalty_exposure)}</strong> },
                { key: "ITR Filed", value: result.itr_filed ? "Yes" : "No" },
              ]}
              testId="health-summary"
            />
          </Card>

          {/* Issues */}
          <Card
            title="Issues Found"
            subtitle={result.issues.length === 0 ? "No issues detected" : `${result.issues.length} issue${result.issues.length !== 1 ? "s" : ""} detected`}
            testId="health-issues-card"
          >
            {result.issues.length === 0 ? (
              <StatusBanner kind="ok" title="No compliance issues found" description="Your tax position appears clean." testId="health-no-issues" />
            ) : (
              <div className="health-issues">
                {result.issues.map((issue, i) => (
                  <IssueRow key={i} issue={issue} />
                ))}
              </div>
            )}
          </Card>

          {/* Recommendations */}
          <Card
            title="Recommendations"
            subtitle={`${result.recommendations.length} actionable item${result.recommendations.length !== 1 ? "s" : ""}`}
            testId="health-recs-card"
          >
            {result.recommendations.length === 0 ? (
              <p className="card__body-text muted">No specific recommendations at this time.</p>
            ) : (
              <div className="health-recs">
                {result.recommendations.map((rec, i) => (
                  <RecommendationRow key={i} rec={rec} index={i} />
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk Analysis Tab
// ---------------------------------------------------------------------------

function RiskAnalysisTab() {
  const [form, setForm] = useState<RiskFormValues>(emptyRiskForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RiskAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setErrors] = useState<Record<string, string>>({});

  const handleChange = <K extends keyof RiskFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
      setErrors((prev) => { const n = { ...prev }; delete n[field]; return n; });
    };

  const submit = useCallback(async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.taxHealth.analyzeRisks({
        tax_outstanding: form.taxOutstanding ? Number(form.taxOutstanding) : undefined,
        notices_count: form.noticesCount ? Number(form.noticesCount) : undefined,
        itr_filed: form.itrFiled,
        wht_shortfall: form.whtShortfall ? Number(form.whtShortfall) : undefined,
        st_shortfall: form.stShortfall ? Number(form.stShortfall) : undefined,
        estimated_income: form.estimatedIncome ? Number(form.estimatedIncome) : undefined,
        declared_income: form.declaredIncome ? Number(form.declaredIncome) : undefined,
      });
      setResult(resp);
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

  return (
    <div className="health-tab">
      <Card title="Risk Analysis Parameters" testId="risk-form-card">
        <form className="health-form" onSubmit={(e) => { e.preventDefault(); void submit(); }} data-testid="risk-form">
          <div className="grid grid--2">
            <Field label="Tax Outstanding (PKR)" data-testid="risk-tax-outstanding" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.taxOutstanding} onChange={handleChange("taxOutstanding")} data-testid="risk-tax-outstanding-input" />
            </Field>
            <Field label="Notices Count" data-testid="risk-notices-count">
              <input type="number" min={0} value={form.noticesCount} onChange={handleChange("noticesCount")} data-testid="risk-notices-count-input" />
            </Field>
          </div>
          <Field label="ITR Filed" data-testid="risk-itr-filed" className="field--checkbox-row">
            <label className="field__checkbox-label">
              <input type="checkbox" checked={form.itrFiled} onChange={handleChange("itrFiled")} data-testid="risk-itr-filed-input" />
              Income Tax Return has been filed
            </label>
          </Field>
          <div className="grid grid--2">
            <Field label="WHT Shortfall (PKR)" data-testid="risk-wht-shortfall" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.whtShortfall} onChange={handleChange("whtShortfall")} data-testid="risk-wht-shortfall-input" />
            </Field>
            <Field label="ST Shortfall (PKR)" data-testid="risk-st-shortfall" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.stShortfall} onChange={handleChange("stShortfall")} data-testid="risk-st-shortfall-input" />
            </Field>
            <Field label="Estimated Income (PKR)" data-testid="risk-estimated-income" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.estimatedIncome} onChange={handleChange("estimatedIncome")} data-testid="risk-estimated-income-input" />
            </Field>
            <Field label="Declared Income (PKR)" data-testid="risk-declared-income" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.declaredIncome} onChange={handleChange("declaredIncome")} data-testid="risk-declared-income-input" />
            </Field>
          </div>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="risk-submit">
              {loading ? "Analyzing risks…" : "Analyze Risks"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setForm(emptyRiskForm()); setResult(null); setError(null); }} data-testid="risk-reset">
              Reset
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Analyzing risk factors…" testId="risk-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Risk analysis failed" description={error} testId="risk-error" />
      ) : null}

      {result && !loading ? (
        <div className="health-result" data-testid="risk-result">
          <Card testId="risk-score-card">
            <div className="health-score-hero">
              <div className="health-score-hero__grade" style={{ color: scoreColor(result.risk_score) }}>
                {result.risk_score}
              </div>
              <div className="health-score-hero__info">
                <p className="card__body-text">Risk Score out of 100</p>
                <Tag variant={riskLevelVariant(result.risk_level)}>{result.risk_level.toUpperCase()} RISK</Tag>
              </div>
            </div>
          </Card>

          <Card title="Risk Factors" subtitle={`${result.factors.length} factor${result.factors.length !== 1 ? "s" : ""} identified`} testId="risk-factors-card">
            {result.factors.length === 0 ? (
              <p className="card__body-text muted">No specific risk factors identified.</p>
            ) : (
              <div className="risk-factors">
                {result.factors.map((factor, i) => (
                  <RiskFactorRow key={i} factor={factor} />
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Penalties Tab
// ---------------------------------------------------------------------------

function PenaltiesTab() {
  const [form, setForm] = useState<PenaltyFormValues>(emptyPenaltyForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = <K extends keyof PenaltyFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const submit = useCallback(async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.taxHealth.estimatePenalties({
        tax_assessed: form.taxAssessed ? Number(form.taxAssessed) : undefined,
        tax_paid: form.taxPaid ? Number(form.taxPaid) : undefined,
        days_late_itr: form.daysLateItr ? Number(form.daysLateItr) : undefined,
        days_late_payment: form.daysLatePayment ? Number(form.daysLatePayment) : undefined,
        wht_shortfall: form.whtShortfall ? Number(form.whtShortfall) : undefined,
        st_shortfall: form.stShortfall ? Number(form.stShortfall) : undefined,
        is_concealment: form.isConcealment,
      });
      setResult(resp);
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

  const renderValue = (val: unknown): React.ReactNode => {
    if (typeof val === "number") return formatPkr(val);
    if (typeof val === "boolean") return val ? "Yes" : "No";
    if (typeof val === "string") return val;
    if (Array.isArray(val)) return val.join(", ");
    return String(val ?? "—");
  };

  return (
    <div className="health-tab">
      <Card title="Penalty Calculator" subtitle="Estimate your penalty exposure based on late filings and shortfalls" testId="penalty-form-card">
        <form className="health-form" onSubmit={(e) => { e.preventDefault(); void submit(); }} data-testid="penalty-form">
          <div className="grid grid--2">
            <Field label="Tax Assessed (PKR)" data-testid="penalty-tax-assessed" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.taxAssessed} onChange={handleChange("taxAssessed")} data-testid="penalty-tax-assessed-input" />
            </Field>
            <Field label="Tax Paid (PKR)" data-testid="penalty-tax-paid" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.taxPaid} onChange={handleChange("taxPaid")} data-testid="penalty-tax-paid-input" />
            </Field>
            <Field label="Days Late (ITR)" data-testid="penalty-days-late-itr">
              <input type="number" min={0} value={form.daysLateItr} onChange={handleChange("daysLateItr")} data-testid="penalty-days-late-itr-input" />
            </Field>
            <Field label="Days Late (Payment)" data-testid="penalty-days-late-payment">
              <input type="number" min={0} value={form.daysLatePayment} onChange={handleChange("daysLatePayment")} data-testid="penalty-days-late-payment-input" />
            </Field>
            <Field label="WHT Shortfall (PKR)" data-testid="penalty-wht-shortfall" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.whtShortfall} onChange={handleChange("whtShortfall")} data-testid="penalty-wht-shortfall-input" />
            </Field>
            <Field label="ST Shortfall (PKR)" data-testid="penalty-st-shortfall" prefix="Rs">
              <input type="number" min={0} step={1000} value={form.stShortfall} onChange={handleChange("stShortfall")} data-testid="penalty-st-shortfall-input" />
            </Field>
          </div>

          <Field label="Concealment of Income" data-testid="penalty-concealment" className="field--checkbox-row">
            <label className="field__checkbox-label">
              <input type="checkbox" checked={form.isConcealment} onChange={handleChange("isConcealment")} data-testid="penalty-concealment-input" />
              Intentional concealment of income is involved (increases penalties significantly)
            </label>
          </Field>

          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="penalty-submit">
              {loading ? "Calculating penalties…" : "Calculate Penalties"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setForm(emptyPenaltyForm()); setResult(null); setError(null); }} data-testid="penalty-reset">
              Reset
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Calculating penalty exposure…" testId="penalty-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Penalty calculation failed" description={error} testId="penalty-error" />
      ) : null}

      {result && !loading ? (
        <Card title="Penalty Estimate" testId="penalty-result-card">
          <Kv
            rows={Object.entries(result).map(([key, val]) => ({
              key: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
              value: renderValue(val),
            }))}
            testId="penalty-result"
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export function HealthPage() {
  const [activeTab, setActiveTab] = useState<Tab>("health");

  const tabs: { id: Tab; label: string }[] = [
    { id: "health", label: "Health Check" },
    { id: "risks", label: "Risk Analysis" },
    { id: "penalties", label: "Penalties" },
  ];

  return (
    <ErrorBoundary>
      <section className="page page--health">
        <header className="page__header">
          <div>
            <h2 className="page__title">Tax Health</h2>
            <p className="page__subtitle">
              Comprehensive tax health assessment with compliance scoring, risk analysis, and penalty estimation.
            </p>
          </div>
        </header>

        <div className="page__tabs" role="tablist" data-testid="health-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={clsx("tab-btn", activeTab === tab.id && "tab-btn--active")}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`health-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="page__content" role="tabpanel">
          {activeTab === "health" && <HealthCheckTab />}
          {activeTab === "risks" && <RiskAnalysisTab />}
          {activeTab === "penalties" && <PenaltiesTab />}
        </div>
      </section>
    </ErrorBoundary>
  );
}
