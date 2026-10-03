import { useState, useCallback } from "react";
import clsx from "clsx";
import { api, ApiError, NetworkError, type TaxHealthResponse } from "@/lib/api";
import { Loading } from "@/components/shell/Loading";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Tag } from "@/components/ui/Tag";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Kv } from "@/components/ui/Kv";

const CURRENT_TAX_YEAR = new Date().getFullYear();

interface ReadinessFormValues {
  ntn: string;
  taxYear: number;
  returnFiled: boolean;
  taxPaid: boolean;
  whtDeposited: boolean;
  stDeposited: boolean;
  bankStatements: boolean;
  form16A: boolean;
  taxAssessed: string;
  taxPaidAmt: string;
  whtCollected: string;
  whtDepositedAmt: string;
  stCollected: string;
  stDepositedAmt: string;
  declaredIncome: string;
  estimatedIncome: string;
}

function emptyForm(): ReadinessFormValues {
  return {
    ntn: localStorage.getItem("fbr_ntn") ?? "",
    taxYear: CURRENT_TAX_YEAR,
    returnFiled: false,
    taxPaid: false,
    whtDeposited: false,
    stDeposited: false,
    bankStatements: false,
    form16A: false,
    taxAssessed: "",
    taxPaidAmt: "",
    whtCollected: "",
    whtDepositedAmt: "",
    stCollected: "",
    stDepositedAmt: "",
    declaredIncome: "",
    estimatedIncome: "",
  };
}

interface ChecklistItem {
  label: string;
  passed: boolean;
  detail?: string;
}

function ReadinessMeter({ score }: { score: number }) {
  const color = score >= 80 ? "ok" : score >= 50 ? "warn" : "err";
  const label =
    score >= 80 ? "Filing Ready" : score >= 50 ? "Partially Ready" : "Not Ready";
  const circumference = 2 * Math.PI * 44;
  const filled = (score / 100) * circumference;

  return (
    <div className="readiness-meter" data-testid="biz-readiness-meter">
      <div className="readiness-meter__ring" aria-hidden>
        <svg viewBox="0 0 100 100" className="readiness-meter__svg">
          {/* Track */}
          <circle
            cx="50"
            cy="50"
            r="44"
            fill="none"
            stroke="var(--c-line)"
            strokeWidth="8"
          />
          {/* Progress */}
          <circle
            cx="50"
            cy="50"
            r="44"
            fill="none"
            stroke={`var(--c-${color})`}
            strokeWidth="8"
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round"
            transform="rotate(-90 50 50)"
            className="readiness-meter__progress"
          />
        </svg>
      </div>
      <div className="readiness-meter__inner">
        <span
          className={clsx("readiness-meter__score", `readiness-meter__score--${color}`)}
          data-testid="biz-readiness-score-value"
        >
          {score}
        </span>
        <span className="readiness-meter__unit">%</span>
        <Tag variant={color as "ok" | "warn" | "err"}>{label}</Tag>
      </div>
    </div>
  );
}

function ChecklistRow({ item }: { item: ChecklistItem }) {
  return (
    <div
      className={clsx("checklist-row", item.passed ? "checklist-row--pass" : "checklist-row--fail")}
      data-testid={`biz-checklist-${item.label.replace(/\s+/g, "-").toLowerCase()}`}
    >
      <span className="checklist-row__icon" aria-hidden>
        {item.passed ? (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="var(--c-ok)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="var(--c-err)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        )}
      </span>
      <span className="checklist-row__label">{item.label}</span>
      {item.detail && <span className="checklist-row__detail muted small">{item.detail}</span>}
      <Tag variant={item.passed ? "ok" : "err"}>{item.passed ? "Pass" : "Fail"}</Tag>
    </div>
  );
}

function computeReadinessScore(
  form: ReadinessFormValues,
  health: TaxHealthResponse
): { score: number; items: ChecklistItem[] } {
  const items: ChecklistItem[] = [];
  let passCount = 0;
  let total = 0;

  const addCheck = (label: string, checkPassed: boolean, detail?: string) => {
    items.push({ label, passed: checkPassed, detail });
    total++;
    if (checkPassed) passCount++;
  };

  addCheck("Business Return Filed", form.returnFiled || health.itr_filed);
  addCheck(
    "Tax Paid",
    form.taxPaid || (health.tax_paid >= (health.tax_assessed || 0))
  );
  addCheck(
    "WHT Deposited",
    form.whtDeposited || (health.wht_deposited >= (health.wht_collected || 0))
  );
  addCheck(
    "Sales Tax Deposited",
    form.stDeposited || (health.st_deposited >= (health.st_collected || 0))
  );
  addCheck("Bank Statements Available", form.bankStatements);
  addCheck("Form 16A Received", form.form16A);
  addCheck(
    "Filing Score",
    (health.filing_score ?? 0) >= 70,
    `${health.filing_score ?? 0}/100`
  );
  addCheck(
    "Deposit Score",
    (health.deposit_score ?? 0) >= 70,
    `${health.deposit_score ?? 0}/100`
  );
  addCheck(
    "Compliance Score",
    (health.compliance_score ?? 0) >= 70,
    `${health.compliance_score ?? 0}/100`
  );
  addCheck(
    "Reconciliation Score",
    (health.reconciliation_score ?? 0) >= 70,
    `${health.reconciliation_score ?? 0}/100`
  );
  addCheck(
    "No Critical Issues",
    (health.critical_issues_count ?? 0) === 0,
    `${health.critical_issues_count ?? 0} critical issues`
  );
  addCheck(
    "Tax Outstanding Clear",
    (health.tax_outstanding ?? 0) === 0,
    `PKR ${(health.tax_outstanding ?? 0).toLocaleString("en-US")} outstanding`
  );

  return {
    score: total > 0 ? Math.round((passCount / total) * 100) : 0,
    items,
  };
}

export function BusinessReadinessPage() {
  const [form, setForm] = useState<ReadinessFormValues>(emptyForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<TaxHealthResponse | null>(null);
  const [ntnError, setNtnError] = useState<string | null>(null);
  const [readinessScore, setReadinessScore] = useState<number | null>(null);
  const [checklistItems, setChecklistItems] = useState<ChecklistItem[]>([]);

  const handleChange =
    <K extends keyof ReadinessFormValues>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: val }));
    };

  const handleNtnChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value.replace(/[^0-9]/g, "").slice(0, 9);
    setForm((prev) => ({ ...prev, ntn: val }));
    if (ntnError) setNtnError(null);
  };

  const checkReadiness = useCallback(async () => {
    setNtnError(null);
    setError(null);

    if (!form.ntn.trim()) {
      setNtnError("Business NTN is required to check return readiness.");
      return;
    }
    if (form.ntn.length < 9) {
      setNtnError("NTN must be at least 9 digits.");
      return;
    }

    localStorage.setItem("fbr_ntn", form.ntn);

    setLoading(true);
    try {
      const response = await api.taxHealth.check({
        ntn: form.ntn,
        tax_year: form.taxYear,
        itr_filed: form.returnFiled || undefined,
        tax_assessed: form.taxAssessed ? Number(form.taxAssessed) : undefined,
        tax_paid: form.taxPaidAmt ? Number(form.taxPaidAmt) : undefined,
        wht_collected: form.whtCollected ? Number(form.whtCollected) : undefined,
        wht_deposited: form.whtDepositedAmt ? Number(form.whtDepositedAmt) : undefined,
        st_collected: form.stCollected ? Number(form.stCollected) : undefined,
        st_deposited: form.stDepositedAmt ? Number(form.stDepositedAmt) : undefined,
        declared_income: form.declaredIncome ? Number(form.declaredIncome) : undefined,
        estimated_income: form.estimatedIncome ? Number(form.estimatedIncome) : undefined,
      });

      setHealth(response);

      const { score, items } = computeReadinessScore(form, response);
      setReadinessScore(score);
      setChecklistItems(items);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Tax health check failed (${err.status}): ${err.detail}`);
      } else if (err instanceof NetworkError) {
        setError(`Network error: ${err.message}. Please check your connection.`);
      } else {
        setError("An unexpected error occurred while checking readiness.");
      }
    } finally {
      setLoading(false);
    }
  }, [form]);

  const reset = useCallback(() => {
    setForm(emptyForm());
    setHealth(null);
    setError(null);
    setNtnError(null);
    setReadinessScore(null);
    setChecklistItems([]);
  }, []);

  return (
    <ErrorBoundary>
      <div className="page page--readiness">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Filing</div>
            <h2 className="page__title">Business Return Readiness</h2>
            <p className="page__subtitle">
              Check whether your business returns can be filed today. Provide your business NTN and tax year to get started.
            </p>
          </div>
          {health && (
            <Button variant="ghost" size="sm" onClick={reset} data-testid="biz-readiness-reset">
              Check another return
            </Button>
          )}
        </header>

        {/* ── Form Card ── */}
        <Card
          title="Your Business Tax Information"
          subtitle="Enter what you know. Partial information still produces a useful readiness estimate."
          testId="biz-readiness-form-card"
        >
          <form
            className="readiness-form"
            onSubmit={(e) => {
              e.preventDefault();
              void checkReadiness();
            }}
            data-testid="biz-readiness-form"
          >
            <div className="grid grid--2">
              <Field
                label="Business NTN (National Tax Number)"
                helperText="9-digit NTN"
                error={ntnError ?? undefined}
                data-testid="biz-readiness-ntn-field"
              >
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{9}"
                  value={form.ntn}
                  onChange={handleNtnChange}
                  placeholder="e.g. 1234567890"
                  maxLength={9}
                  data-testid="biz-readiness-ntn-input"
                />
              </Field>

              <Field
                label="Tax Year"
                helperText="The tax year you are filing for"
                data-testid="biz-readiness-tax-year-field"
              >
                <Select
                  value={String(form.taxYear)}
                  onChange={(v) => setForm((prev) => ({ ...prev, taxYear: Number(v) }))}
                  testId="biz-readiness-tax-year-select"
                  ariaLabel="Tax year"
                  options={Array.from({ length: 6 }, (_, i) => CURRENT_TAX_YEAR - i).map((yr) => ({
                    value: String(yr),
                    label: `Tax Year ${yr}`,
                  }))}
                />
              </Field>

              <Field
                label="Declared Business Income (PKR)"
                helperText="As reported in your return"
                data-testid="biz-readiness-income-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.declaredIncome}
                  onChange={handleChange("declaredIncome")}
                  placeholder="e.g. 12000000"
                  data-testid="biz-readiness-income-input"
                />
              </Field>

              <Field
                label="Estimated Business Income (PKR)"
                helperText="Total income for the year"
                data-testid="biz-readiness-est-income-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.estimatedIncome}
                  onChange={handleChange("estimatedIncome")}
                  placeholder="e.g. 15000000"
                  data-testid="biz-readiness-est-income-input"
                />
              </Field>

              <Field
                label="Tax Assessed (PKR)"
                helperText="Tax calculated by FBR"
                data-testid="biz-readiness-tax-assessed-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.taxAssessed}
                  onChange={handleChange("taxAssessed")}
                  placeholder="e.g. 1500000"
                  data-testid="biz-readiness-tax-assessed-input"
                />
              </Field>

              <Field
                label="Tax Paid (PKR)"
                helperText="Tax already paid (withholding, advance)"
                data-testid="biz-readiness-tax-paid-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.taxPaidAmt}
                  onChange={handleChange("taxPaidAmt")}
                  placeholder="e.g. 1200000"
                  data-testid="biz-readiness-tax-paid-input"
                />
              </Field>

              <Field
                label="WHT Collected (PKR)"
                helperText="Withholding tax deducted at source"
                data-testid="biz-readiness-wht-collected-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.whtCollected}
                  onChange={handleChange("whtCollected")}
                  placeholder="e.g. 500000"
                  data-testid="biz-readiness-wht-collected-input"
                />
              </Field>

              <Field
                label="WHT Deposited (PKR)"
                helperText="WHT deposited with FBR"
                data-testid="biz-readiness-wht-deposited-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.whtDepositedAmt}
                  onChange={handleChange("whtDepositedAmt")}
                  placeholder="e.g. 450000"
                  data-testid="biz-readiness-wht-deposited-input"
                />
              </Field>

              <Field
                label="ST Collected (PKR)"
                helperText="Sales tax collected"
                data-testid="biz-readiness-st-collected-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.stCollected}
                  onChange={handleChange("stCollected")}
                  placeholder="e.g. 200000"
                  data-testid="biz-readiness-st-collected-input"
                />
              </Field>

              <Field
                label="ST Deposited (PKR)"
                helperText="Sales tax deposited with FBR"
                data-testid="biz-readiness-st-deposited-field"
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.stDepositedAmt}
                  onChange={handleChange("stDepositedAmt")}
                  placeholder="e.g. 200000"
                  data-testid="biz-readiness-st-deposited-input"
                />
              </Field>
            </div>

            {/* Checkboxes */}
            <fieldset className="readiness-checkboxes">
              <legend className="readiness-checkboxes__legend">Business filing status</legend>

              <div className="readiness-checkboxes__grid">
              <label className="readiness-checkbox">
                <input
                  type="checkbox"
                  checked={form.returnFiled}
                  onChange={handleChange("returnFiled")}
                  data-testid="biz-readiness-return-filed"
                />
                <span>Business return filed</span>
              </label>

              <label className="readiness-checkbox">
                <input
                  type="checkbox"
                  checked={form.taxPaid}
                  onChange={handleChange("taxPaid")}
                  data-testid="biz-readiness-tax-paid"
                />
                <span>Tax paid or withheld at source</span>
              </label>

              <label className="readiness-checkbox">
                <input
                  type="checkbox"
                  checked={form.whtDeposited}
                  onChange={handleChange("whtDeposited")}
                  data-testid="biz-readiness-wht-deposited"
                />
                <span>WHT deposited with FBR</span>
              </label>

              <label className="readiness-checkbox">
                <input
                  type="checkbox"
                  checked={form.stDeposited}
                  onChange={handleChange("stDeposited")}
                  data-testid="biz-readiness-st-deposited"
                />
                <span>Sales tax deposited with FBR</span>
              </label>

              <label className="readiness-checkbox">
                <input
                  type="checkbox"
                  checked={form.bankStatements}
                  onChange={handleChange("bankStatements")}
                  data-testid="biz-readiness-bank-statements"
                />
                <span>Business bank statements available</span>
              </label>

              <label className="readiness-checkbox">
                <input
                  type="checkbox"
                  checked={form.form16A}
                  onChange={handleChange("form16A")}
                  data-testid="biz-readiness-form-16a"
                />
                <span>Form 16A (WHT certificate) received</span>
              </label>
              </div>
            </fieldset>

            <div className="form__actions">
              <Button
                type="submit"
                variant="primary"
                loading={loading}
                disabled={loading}
                data-testid="biz-readiness-submit"
              >
                {loading ? "Analyzing readiness…" : "Check Business Return Readiness"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={reset}
                data-testid="biz-readiness-reset-form"
              >
                Reset
              </Button>
            </div>
          </form>
        </Card>

        {/* Error state */}
        {error && (
          <StatusBanner
            kind="err"
            title="Could not check readiness"
            description={error}
            testId="biz-readiness-error"
          />
        )}

        {/* Loading state */}
        {loading && (
          <Card testId="biz-readiness-loading-card">
            <Loading label="Analyzing your business tax information and computing readiness…" testId="biz-readiness-loading" />
          </Card>
        )}

        {/* Results */}
        {health && readinessScore !== null && !loading && (
          <div className="readiness-results" data-testid="biz-readiness-results">
            {/* Readiness Meter */}
            <section className="readiness__meter-section" data-testid="biz-readiness-meter-section">
              <Card title="Business Return Readiness Score" testId="biz-readiness-score-card">
                <div className="readiness__meter-layout">
                  <ReadinessMeter score={readinessScore} />
                  <div className="readiness__meter-stats">
                    <Kv
                      rows={[
                        {
                          key: "Business Return Filed",
                          value: health.itr_filed ? <Tag variant="ok">Yes</Tag> : <Tag variant="err">No</Tag>,
                        },
                        {
                          key: "Filing Score",
                          value: `${health.filing_score}/100`,
                        },
                        {
                          key: "Deposit Score",
                          value: `${health.deposit_score}/100`,
                        },
                        {
                          key: "Compliance Score",
                          value: `${health.compliance_score}/100`,
                        },
                        {
                          key: "Reconciliation Score",
                          value: `${health.reconciliation_score}/100`,
                        },
                        {
                          key: "Health Grade",
                          value: <Tag variant={health.health_grade === "A" || health.health_grade === "B" ? "ok" : "warn"}>{health.health_grade}</Tag>,
                        },
                        {
                          key: "Risk Level",
                          value: <Tag variant={health.risk_level === "low" ? "ok" : health.risk_level === "medium" ? "warn" : "err"}>{health.risk_level}</Tag>,
                        },
                      ]}
                      testId="biz-readiness-kv"
                    />
                  </div>
                </div>
              </Card>
            </section>

            {/* Checklist */}
            <section className="readiness__checklist-section" data-testid="biz-readiness-checklist-section">
              <Card
                title="Business Readiness Checklist"
                subtitle={`${checklistItems.filter((i) => i.passed).length}/${checklistItems.length} checks passed`}
                testId="biz-readiness-checklist-card"
              >
                <div className="checklist">
                  {checklistItems.map((item) => (
                    <ChecklistRow key={item.label} item={item} />
                  ))}
                </div>
              </Card>
            </section>

            {/* Health Issues */}
            {health.issues && health.issues.length > 0 && (
              <section className="readiness__issues-section" data-testid="biz-readiness-issues-section">
                <Card
                  title="Business Tax Health Issues"
                  subtitle={`${health.critical_issues_count} critical · ${health.issues.length} total`}
                  testId="biz-readiness-issues-card"
                >
                  <div className="issues-list">
                    {health.issues.map((issue, idx) => (
                      <div key={idx} className="issue-row" data-testid={`biz-readiness-issue-${idx}`}>
                        <div className="issue-row__header">
                          <span className="issue-row__code mono">{issue.code}</span>
                          <Tag
                            variant={
                              issue.severity === "critical"
                                ? "err"
                                : issue.severity === "high"
                                ? "warn"
                                : "default"
                            }
                          >
                            {issue.severity}
                          </Tag>
                        </div>
                        <p className="issue-row__title">{issue.title}</p>
                        <p className="issue-row__desc muted small">{issue.description}</p>
                        <div className="issue-row__meta">
                          <span>
                            Tax impact:{" "}
                            <strong>PKR {issue.tax_impact.toLocaleString("en-US")}</strong>
                          </span>
                          <span>
                            Est. penalty:{" "}
                            <strong>PKR {issue.penalty_estimate.toLocaleString("en-US")}</strong>
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </section>
            )}

            {/* Recommendations */}
            {health.recommendations && health.recommendations.length > 0 && (
              <section className="readiness__recs-section" data-testid="biz-readiness-recs-section">
                <Card title="Recommendations" testId="biz-readiness-recs-card">
                  <div className="recs-list">
                    {health.recommendations.map((rec, idx) => (
                      <div key={idx} className="rec-row" data-testid={`biz-readiness-rec-${idx}`}>
                        <div className="rec-row__header">
                          <Tag
                            variant={
                              rec.priority === "critical"
                                ? "err"
                                : rec.priority === "high"
                                ? "warn"
                                : "accent"
                            }
                          >
                            {rec.priority}
                          </Tag>
                          {rec.deadline && (
                            <span className="rec-row__deadline muted small">
                              Due: {rec.deadline}
                            </span>
                          )}
                        </div>
                        <p className="rec-row__action">{rec.action}</p>
                        <p className="rec-row__reason muted small">{rec.reason}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              </section>
            )}

            {/* Financial Summary */}
            <section className="readiness__fin-section" data-testid="biz-readiness-fin-section">
              <Card
                title="Business Financial Summary"
                subtitle={`Tax Year ${health.tax_year} · NTN: ${health.ntn.replace(/(\d{4})(\d{3})(\d{3})/, "$1-$2-$3")}`}
                testId="biz-readiness-fin-card"
              >
                <Kv
                  rows={[
                    {
                      key: "Declared Business Income",
                      value: `PKR ${health.declared_income.toLocaleString("en-US")}`,
                    },
                    {
                      key: "Estimated Business Income",
                      value: `PKR ${health.estimated_income.toLocaleString("en-US")}`,
                    },
                    {
                      key: "Tax Assessed",
                      value: `PKR ${health.tax_assessed.toLocaleString("en-US")}`,
                    },
                    {
                      key: "Tax Paid",
                      value: `PKR ${health.tax_paid.toLocaleString("en-US")}`,
                    },
                    {
                      key: "Tax Outstanding",
                      value: (
                        <Tag variant={health.tax_outstanding > 0 ? "err" : "ok"}>
                          PKR {health.tax_outstanding.toLocaleString("en-US")}
                        </Tag>
                      ),
                    },
                    {
                      key: "WHT Collected",
                      value: `PKR ${health.wht_collected.toLocaleString("en-US")}`,
                    },
                    {
                      key: "WHT Deposited",
                      value: `PKR ${health.wht_deposited.toLocaleString("en-US")}`,
                    },
                    {
                      key: "WHT Shortfall",
                      value: (
                        <Tag variant={health.wht_shortfall > 0 ? "warn" : "ok"}>
                          PKR {health.wht_shortfall.toLocaleString("en-US")}
                        </Tag>
                      ),
                    },
                    {
                      key: "ST Collected",
                      value: `PKR ${health.st_collected.toLocaleString("en-US")}`,
                    },
                    {
                      key: "ST Deposited",
                      value: `PKR ${health.st_deposited.toLocaleString("en-US")}`,
                    },
                    {
                      key: "ST Shortfall",
                      value: (
                        <Tag variant={health.st_shortfall > 0 ? "warn" : "ok"}>
                          PKR ${health.st_shortfall.toLocaleString("en-US")}
                        </Tag>
                      ),
                    },
                    {
                      key: "Total Penalty Exposure",
                      value: (
                        <Tag variant={health.total_penalty_exposure > 0 ? "err" : "ok"}>
                          PKR {health.total_penalty_exposure.toLocaleString("en-US")}
                        </Tag>
                      ),
                    },
                  ]}
                  testId="biz-readiness-fin-kv"
                />
              </Card>
            </section>

            {/* Action Items */}
            <section className="readiness__actions-section" data-testid="biz-readiness-actions-section">
              <Card title="Action Items to Reach 100%" testId="biz-readiness-actions-card">
                {readinessScore >= 100 ? (
                  <StatusBanner
                    kind="ok"
                    title="You are 100% ready to file your business return!"
                    description="All readiness checks have passed. You can file your business return now."
                    testId="biz-readiness-fully-ready"
                  />
                ) : (
                  <ul className="action-items">
                    {checklistItems
                      .filter((item) => !item.passed)
                      .map((item) => (
                        <li key={item.label} className="action-item">
                          <span className="action-item__icon" aria-hidden>
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="var(--c-warn)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                              <circle cx="12" cy="12" r="10" />
                              <line x1="12" x2="12" y1="8" y2="12" />
                              <line x1="12" x2="12.01" y1="16" y2="16" />
                            </svg>
                          </span>
                          <span className="action-item__text">{item.label}</span>
                        </li>
                      ))}
                  </ul>
                )}
              </Card>
            </section>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}