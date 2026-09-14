import { useState, useEffect, useCallback } from "react";
import clsx from "clsx";
import { api, ApiError, type CalendarDashboard, type UpcomingTask, type TaxHealthResponse, type VerificationResponse } from "@/lib/api";
import { Loading } from "@/components/shell/Loading";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Tag } from "@/components/ui/Tag";
import { Kv } from "@/components/ui/Kv";
import { Button } from "@/components/ui/Button";
import { useNotification } from "@/state/notifications";

type TaxpayerType = "individual" | "business" | "company" | "aop";

interface DashboardState {
  calendar: CalendarDashboard | null;
  upcoming: UpcomingTask[];
  taxHealth: TaxHealthResponse | null;
  filerStatus: VerificationResponse | null;
  noticeTypes: string[];
}

function gradeColor(grade: string): string {
  const g = grade?.toUpperCase();
  if (g === "A" || g === "A+" || g === "A-") return "ok";
  if (g === "B" || g === "B+") return "accent";
  if (g === "C" || g === "B-") return "warn";
  return "err";
}

function scoreColor(score: number): string {
  if (score >= 80) return "ok";
  if (score >= 60) return "accent";
  if (score >= 40) return "warn";
  return "err";
}

function formatNtn(ntn: string): string {
  if (!ntn) return "—";
  return ntn.replace(/(\d{4})(\d{3})(\d{3})/, "$1-$2-$3");
}

function StatCard({
  label,
  value,
  unit,
  grade,
  variant = "default",
  badge,
  testId,
}: {
  label: string;
  value: string | number;
  unit?: string;
  grade?: string;
  variant?: "default" | "large";
  badge?: React.ReactNode;
  testId?: string;
}) {
  return (
    <div
      className={clsx("stat-card", variant === "large" && "stat-card--large")}
      data-testid={testId}
    >
      <div className="stat-card__label eyebrow">{label}</div>
      <div className="stat-card__value-row">
        <span
          className={clsx(
            "stat-card__value",
            grade && `stat-card__value--${gradeColor(grade)}`
          )}
        >
          {value}
        </span>
        {unit && <span className="stat-card__unit">{unit}</span>}
        {grade && (
          <Tag variant={gradeColor(grade) as "ok" | "accent" | "warn" | "err"} className="stat-card__grade">
            {grade}
          </Tag>
        )}
      </div>
      {badge && <div className="stat-card__badge">{badge}</div>}
    </div>
  );
}

function QuickActionCard({
  icon,
  title,
  description,
  href,
  onClick,
  testId,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href?: string;
  onClick?: () => void;
  testId?: string;
}) {
  return (
    <div className="qaction" data-testid={testId}>
      <div className="qaction__icon" aria-hidden>{icon}</div>
      <div className="qaction__body">
        <h4 className="qaction__title">{title}</h4>
        <p className="qaction__desc">{description}</p>
      </div>
      {href ? (
        <a href={href} className="qaction__link btn btn--ghost btn--sm">
          Open
        </a>
      ) : (
        <Button variant="ghost" size="sm" onClick={onClick}>
          Open
        </Button>
      )}
    </div>
  );
}

function UpcomingTaskRow({ task }: { task: UpcomingTask }) {
  return (
    <div
      className={clsx(
        "task-row",
        task.is_overdue && "task-row--overdue",
        task.urgency === "critical" && "task-row--critical"
      )}
      data-testid="biz-upcoming-task"
    >
      <div className="task-row__left">
        <span className="task-row__title">{task.title}</span>
        <span className="task-row__meta">
          {task.category} &middot; {task.event_type}
        </span>
      </div>
      <div className="task-row__right">
        {task.is_overdue ? (
          <Tag variant="err">Overdue</Tag>
        ) : (
          <Tag
            variant={
              task.urgency === "critical"
                ? "err"
                : task.urgency === "high"
                ? "warn"
                : "default"
            }
          >
            {task.days_remaining}d
          </Tag>
        )}
        <span className="task-row__date">
          {new Date(task.due_date).toLocaleDateString("en-PK", {
            month: "short",
            day: "numeric",
          })}
        </span>
      </div>
    </div>
  );
}

export function BusinessOverviewPage() {
  const [taxpayerType, setTaxpayerType] = useState<TaxpayerType>("business");
  const [ntn] = useState(() => localStorage.getItem("fbr_ntn") ?? "");
  const [loading, setLoading] = useState(true);
  const [fetchErrors, setFetchErrors] = useState<string[]>([]);
  const [state, setState] = useState<DashboardState>({
    calendar: null,
    upcoming: [],
    taxHealth: null,
    filerStatus: null,
    noticeTypes: [],
  });
  const { show: notify } = useNotification();

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setFetchErrors([]);
    const errors: string[] = [];

    const [calDash, upcomingTasks, ntnVal, taxYr] = await Promise.all([
      api.calendar.getDashboard(taxpayerType).catch((e) => {
        errors.push(e instanceof ApiError ? `Calendar: ${e.detail}` : "Calendar: network error");
        return null;
      }),
      api.calendar.getUpcoming(taxpayerType, 30).catch((e) => {
        errors.push(e instanceof ApiError ? `Upcoming: ${e.detail}` : "Upcoming: network error");
        return [];
      }),
      Promise.resolve((ntn || localStorage.getItem("fbr_ntn")) ?? ""),
      Promise.resolve(new Date().getFullYear()),
    ]);

    const [taxHealth, filerStatus, noticeTypes] = await Promise.all([
      ntnVal.length >= 9
        ? api.taxHealth.check({ ntn: ntnVal, tax_year: taxYr as number }).catch((e) => {
            errors.push(e instanceof ApiError ? `Tax Health: ${e.detail}` : "Tax Health: network error");
            return null;
          })
        : Promise.resolve(null),
      ntnVal.length >= 9
        ? api.verify.filer(ntnVal).catch((e) => {
            errors.push(e instanceof ApiError ? `Filer Status: ${e.detail}` : "Filer Status: network error");
            return null;
          })
        : Promise.resolve(null),
      api.notices.getTypes().catch((e) => {
        errors.push(e instanceof ApiError ? `Notices: ${e.detail}` : "Notices: network error");
        return { total: 0, notice_types: [] as string[], categories: [] as string[] };
      }),
    ]);

    setFetchErrors(errors);
    setState({
      calendar: calDash,
      upcoming: upcomingTasks,
      taxHealth,
      filerStatus,
      noticeTypes: (noticeTypes as { notice_types: string[] }).notice_types ?? [],
    });
    setLoading(false);
  }, [taxpayerType, ntn]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const { calendar, upcoming, taxHealth, filerStatus } = state;
  const complianceScore = calendar?.compliance_score ?? taxHealth?.compliance_score ?? 0;
  const complianceGrade = calendar?.compliance_grade ?? taxHealth?.health_grade ?? "—";
  const overdueCount = calendar?.overdue_count ?? 0;
  const critical7d = calendar?.critical_upcoming_7d ?? 0;
  const total30d = calendar?.total_events ?? upcoming.length;
  const healthScore = taxHealth?.health_score ?? 0;
  const healthGrade = taxHealth?.health_grade ?? "—";
  const isFiler = filerStatus?.is_verified ?? null;
  const pendingNotices = state.noticeTypes.length;

  const readinessPct = taxHealth
    ? Math.round(
        ((taxHealth.filing_score + taxHealth.deposit_score + taxHealth.compliance_score) / 3) * 10
      ) / 10
    : null;

  const handleRefresh = () => {
    void fetchAll();
    notify("ok", "Business dashboard refreshed");
  };

  if (loading) {
    return (
      <div className="page page--overview">
        <header className="page__header">
          <p className="page-eyebrow">Business · Overview</p>
            <h2 className="page__title">Business Overview</h2>
        </header>
        <Loading label="Loading your business dashboard…" testId="biz-loading" />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="page page--overview">
        <header className="page__header">
          <div>
            <p className="page-eyebrow">Business · Overview</p>
            <h2 className="page__title">Business Overview</h2>
            <p className="page__subtitle">Your business tax snapshot: sales tax, withholding, and upcoming filing deadlines.</p>
          </div>
          <div className="page__header-controls">
            <label className="field__label" htmlFor="biz-taxpayer-type">
              Taxpayer Type
            </label>
            <select
              id="biz-taxpayer-type"
              className="page__select"
              value={taxpayerType}
              onChange={(e) => setTaxpayerType(e.target.value as TaxpayerType)}
              data-testid="biz-taxpayer-type"
            >
              <option value="business">Business</option>
              <option value="company">Company</option>
              <option value="aop">AOP</option>
              <option value="individual">Individual</option>
            </select>
            <Button variant="ghost" size="sm" onClick={handleRefresh} data-testid="biz-refresh">
              Refresh
            </Button>
          </div>
        </header>

        {fetchErrors.length > 0 && (
          <StatusBanner
            kind="err"
            title="Some data could not be loaded"
            description={fetchErrors.join(". ")}
            testId="biz-fetch-errors"
          />
        )}

        {/* ── Tax Status Snapshot ── */}
        <section className="overview__snapshot" aria-label="Business tax status snapshot" data-testid="biz-snapshot">
          <div className="snapshot__score-block">
            <div className="snapshot__eyebrow eyebrow">Compliance Score</div>
            <div className="snapshot__score-row">
              <span
                className={clsx("snapshot__score", `snapshot__score--${scoreColor(complianceScore)}`)}
                data-testid="biz-compliance-score"
              >
                {complianceScore}
              </span>
              <Tag variant={gradeColor(complianceGrade) as "ok" | "accent" | "warn" | "err"} className="snapshot__grade">
                {complianceGrade}
              </Tag>
            </div>
            <p className="snapshot__caption">
              {calendar?.summary_message ?? taxHealth?.risk_level ?? "Based on available data"}
            </p>
          </div>

          <div className="snapshot__divider" aria-hidden />

          <div className="snapshot__metrics">
            <StatCard
              label="Upcoming (30d)"
              value={total30d}
              unit="filings"
              testId="biz-upcoming-total"
            />
            <StatCard
              label="Overdue"
              value={overdueCount}
              badge={overdueCount > 0 ? <Tag variant="err">{overdueCount} overdue</Tag> : undefined}
              testId="biz-overdue"
            />
            <StatCard
              label="Critical (7d)"
              value={critical7d}
              badge={critical7d > 0 ? <Tag variant="err">{critical7d} critical</Tag> : undefined}
              testId="biz-critical-7d"
            />
          </div>
        </section>

        {/* ── Quick Stats ── */}
        <section className="overview__stats" aria-label="Business quick statistics" data-testid="biz-stats">
          <Card title="Business Statistics" testId="biz-stats-card">
            <div className="stats-grid">
              <StatCard
                label="Tax Health"
                value={healthScore}
                unit="/100"
                grade={healthGrade}
                testId="biz-health-score"
              />
              <StatCard
                label="Filer Status"
                value={isFiler === null ? "—" : isFiler ? "Active Filer" : "Non-Filer"}
                badge={
                  isFiler !== null ? (
                    <Tag variant={isFiler ? "ok" : "err"}>
                      {isFiler ? "Verified" : "Not on ATL"}
                    </Tag>
                  ) : (
                    <Tag variant="default">Not checked</Tag>
                  )
                }
                testId="biz-filer-status"
              />
              <StatCard
                label="Notice Types"
                value={pendingNotices}
                badge={
                  pendingNotices > 0 ? (
                    <Tag variant="warn">{pendingNotices} types available</Tag>
                  ) : undefined
                }
                testId="biz-pending-notices"
              />
              <StatCard
                label="Return Readiness"
                value={readinessPct !== null ? `${readinessPct}%` : "—"}
                badge={
                  readinessPct !== null ? (
                    <Tag variant={readinessPct >= 80 ? "ok" : readinessPct >= 50 ? "warn" : "err"}>
                      {readinessPct >= 80 ? "Ready" : readinessPct >= 50 ? "Partial" : "Not ready"}
                    </Tag>
                  ) : undefined
                }
                testId="biz-readiness"
              />
            </div>
          </Card>
        </section>

        {/* ── Tax Health Detail ── */}
        {taxHealth ? (
          <section className="overview__health" data-testid="biz-health-detail">
            <Card
              title="Tax Health Detail"
              subtitle={`Tax year ${taxHealth.tax_year} · NTN: ${formatNtn(taxHealth.ntn)}`}
              testId="biz-health-card"
            >
              <Kv
                rows={[
                  { key: "Business Return Filed", value: taxHealth.itr_filed ? <Tag variant="ok">Yes</Tag> : <Tag variant="err">No</Tag> },
                  ...(taxHealth.itr_due_date ? [{ key: "Business Return Due", value: taxHealth.itr_due_date }] : []),
                  { key: "Declared Income", value: `PKR ${taxHealth.declared_income.toLocaleString("en-US")}` },
                  { key: "Tax Assessed", value: `PKR ${taxHealth.tax_assessed.toLocaleString("en-US")}` },
                  { key: "Tax Paid", value: `PKR ${taxHealth.tax_paid.toLocaleString("en-US")}` },
                  {
                    key: "Tax Outstanding",
                    value: (
                      <Tag variant={taxHealth.tax_outstanding > 0 ? "err" : "ok"}>
                        PKR {taxHealth.tax_outstanding.toLocaleString("en-US")}
                      </Tag>
                    ),
                  },
                  { key: "WHT Shortfall", value: `PKR ${taxHealth.wht_shortfall.toLocaleString("en-US")}` },
                  { key: "Sales Tax Shortfall", value: `PKR ${taxHealth.st_shortfall.toLocaleString("en-US")}` },
                  { key: "Filing Score", value: `${taxHealth.filing_score}/100` },
                  { key: "Deposit Score", value: `${taxHealth.deposit_score}/100` },
                  { key: "Reconciliation Score", value: `${taxHealth.reconciliation_score}/100` },
                  {
                    key: "Critical Issues",
                    value: (
                      <Tag variant={taxHealth.critical_issues_count > 0 ? "err" : "ok"}>
                        {taxHealth.critical_issues_count}
                      </Tag>
                    ),
                  },
                  {
                    key: "Penalty Exposure",
                    value: `PKR ${taxHealth.total_penalty_exposure.toLocaleString("en-US")}`,
                  },
                ]}
                testId="biz-health-kv"
              />
            </Card>
          </section>
        ) : null}

        {/* ── Quick Actions ── */}
        <section className="overview__actions" aria-label="Business quick actions" data-testid="biz-actions">
          <Card title="Quick Actions" testId="biz-actions-card">
            <div className="qactions">
              <QuickActionCard
                icon={
                  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
                    <line x1="16" x2="16" y1="2" y2="6"/>
                    <line x1="8" x2="8" y1="2" y2="6"/>
                    <line x1="3" x2="21" y1="10" y2="10"/>
                  </svg>
                }
                title="Filing Calendar"
                description="View company and sales tax deadlines, and track compliance events."
                testId="biz-action-calendar"
              />
              <QuickActionCard
                icon={
                  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14,2 14,8 20,8"/>
                    <line x1="16" x2="8" y1="13" y2="13"/>
                    <line x1="16" x2="8" y1="17" y2="17"/>
                    <polyline points="10,9 9,9 8,9"/>
                  </svg>
                }
                title="Notices"
                description="Analyze FBR notices, view action plans, and understand appeal options."
                testId="biz-action-notices"
              />
              <QuickActionCard
                icon={
                  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                  </svg>
                }
                title="Tax Health"
                description="Deep-dive compliance signals, sales tax exposure, and risk analysis."
                testId="biz-action-health"
              />
              <QuickActionCard
                icon={
                  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                    <polyline points="13,2 13,9 20,9"/>
                  </svg>
                }
                title="Documents"
                description="Upload and verify business tax documents, extract data, and parse forms."
                testId="biz-action-documents"
              />
            </div>
          </Card>
        </section>

        {/* ── Upcoming Tasks ── */}
        <section className="overview__upcoming" data-testid="biz-upcoming-section">
          <Card
            title="Upcoming Filing Tasks"
            subtitle={`${upcoming.length} tasks in the next 30 days`}
            action={
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefresh}
                data-testid="biz-refresh-tasks"
              >
                Refresh
              </Button>
            }
            testId="biz-upcoming-card"
          >
            {upcoming.length === 0 ? (
              <p className="card__body-text" data-testid="biz-no-upcoming">
                No upcoming tasks. Your business compliance calendar is clear for the next 30 days.
              </p>
            ) : (
              <div className="task-list">
                {upcoming.slice(0, 10).map((task) => (
                  <UpcomingTaskRow key={task.event_id} task={task} />
                ))}
                {upcoming.length > 10 && (
                  <p className="overview__more muted">
                    +{upcoming.length - 10} more tasks in the next 30 days
                  </p>
                )}
              </div>
            )}
          </Card>
        </section>
      </div>
    </ErrorBoundary>
  );
}