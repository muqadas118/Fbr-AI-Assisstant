import { useState, useCallback } from "react";
import {
  api,
  ApiError,
  NetworkError,
  type NoticeAnalysisResponse,
  type ActionStep,
  type AppealGuide,
} from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Loading } from "@/components/shell/Loading";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Field } from "@/components/ui/Field";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";

// ─── Helpers ───────────────────────────────────────────────────────────────

function formatDate(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-PK", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatPkr(val: number | undefined): string {
  if (val == null) return "—";
  return `PKR ${val.toLocaleString("en-US")}`;
}

function confidenceVariant(c: number): "ok" | "warn" | "err" {
  if (c >= 0.85) return "ok";
  if (c >= 0.6) return "warn";
  return "err";
}

function urgencyVariant(u: string): "err" | "warn" | "accent" | "default" {
  switch (u) {
    case "critical": return "err";
    case "high": return "warn";
    case "medium": return "accent";
    default: return "default";
  }
}

function priorityTagVariant(p: string): "err" | "warn" | "accent" | "default" {
  switch (p) {
    case "critical": return "err";
    case "high": return "warn";
    case "medium": return "accent";
    default: return "default";
  }
}

// ─── Business Notice Types Reference ────────────────────────────────────────

const BUSINESS_NOTICE_TYPES_REFERENCE = [
  "Sales Tax Notice – Section 14 (Response to Notice)",
  "Sales Tax Notice – Section 33 (Production of Records)",
  "Sales Tax Return Filing Default Notice",
  "Input Tax Adjustment / ITC Disallowance Notice",
  "Sales Tax Recovery / Demand Notice",
  "Federal Excise Duty Notice",
  "Withholding Tax (WHT) Statement Notice",
  "Section 161/165 Withholding Adjustment Notice",
  "Company Income Tax Notice – Section 122",
  "Corporate Audit Notice",
  "Penalty Notice (Company / AOP)",
  "Business Re-assessment Notice",
  "Advance Tax Notice (Company)",
  "Annual Business Return Notice",
  "Default / Non-Filing Notice",
];

// ─── Collapsible Text ───────────────────────────────────────────────────────

function CollapsibleText({ title, text, initiallyOpen = false }: {
  title: string;
  text: string;
  initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <div className="notice-collapse">
      <button
        className="notice-collapse__toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        data-testid={`biz-collapse-${title.toLowerCase().replace(/\s+/g, "-")}`}
      >
        <span>{open ? "▾" : "▸"}</span>
        {title}
      </button>
      {open && (
        <div className="notice-collapse__body">
          <pre className="notice-collapse__text">{text}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Action Plan ─────────────────────────────────────────────────────────────

function ActionPlanView({ plan }: { plan: NonNullable<NoticeAnalysisResponse["action_plan"]> }) {
  return (
    <Card title="Business Action Plan" subtitle={`${plan.total_steps} steps · ~${plan.estimated_total_hours}h estimated`} testId="biz-action-plan">
      <p className="notice-plan__summary">{plan.summary}</p>

      {plan.requires_professional_help && (
        <StatusBanner
          kind="warn"
          title="Professional help recommended"
          description="This business notice is complex. Consider consulting a tax advisor, auditor, or legal counsel."
          testId="biz-professional-help"
        />
      )}

      {plan.requires_payment && (
        <StatusBanner
          kind="info"
          title="Payment may be required"
          description="The action plan may involve sales tax or withholding payment. Ensure you have documented evidence of any payments made."
          testId="biz-payment-notice"
        />
      )}

      <ol className="notice-steps" data-testid="biz-steps">
        {plan.steps.map((step: ActionStep) => (
          <li key={step.step_number} className="notice-step" data-testid={`biz-step-${step.step_number}`}>
            <div className="notice-step__head">
              <strong className="notice-step__title">Step {step.step_number}: {step.title}</strong>
              <div className="notice-step__badges">
                <Tag variant={priorityTagVariant(step.priority)}>{step.priority}</Tag>
                <Tag variant="default">~{step.estimated_hours}h</Tag>
              </div>
            </div>
            <p className="notice-step__desc">{step.description}</p>
            {step.documents_needed.length > 0 && (
              <div className="notice-step__docs">
                <span className="notice-step__docs-label">Business documents needed:</span>
                <ul>
                  {step.documents_needed.map((doc, i) => (
                    <li key={i}>{doc}</li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        ))}
      </ol>

      {plan.common_mistakes.length > 0 && (
        <div className="notice-plan__tips">
          <h4 className="notice-plan__tips-title">Common Mistakes to Avoid</h4>
          <ul>
            {plan.common_mistakes.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {plan.helpful_tips.length > 0 && (
        <div className="notice-plan__tips">
          <h4 className="notice-plan__tips-title">Helpful Tips</h4>
          <ul>
            {plan.helpful_tips.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

// ─── Appeal Guide ───────────────────────────────────────────────────────────

function AppealGuideView({ guide }: { guide: AppealGuide }) {
  return (
    <Card
      title="Appeal Guide"
      subtitle={guide.is_appealable ? "This business notice may be appealable" : "This business notice is not typically appealable"}
      testId="biz-appeal-guide"
    >
      {!guide.is_appealable ? (
        <StatusBanner
          kind="info"
          title="Not appealable"
          description="This type of business notice is generally not subject to appeal. Follow the action plan steps instead."
          testId="biz-not-appealable"
        />
      ) : (
        <>
          <Kv
            rows={[
              { key: "Forum", value: <strong>{guide.forum}</strong> },
              { key: "Time Limit", value: <Tag variant="warn">{guide.time_limit_days} days</Tag> },
              { key: "Fees", value: guide.fees_required || "—" },
              { key: "Success Rate", value: guide.typical_success_rate || "—" },
              { key: "Est. Cost", value: guide.estimated_cost || "—" },
            ]}
            testId="biz-appeal-kv"
          />

          {guide.forms_required.length > 0 && (
            <div className="notice-appeal__section">
              <h4 className="notice-appeal__section-title">Forms Required</h4>
              <ul className="notice-appeal__list">
                {guide.forms_required.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          {guide.documents_needed.length > 0 && (
            <div className="notice-appeal__section">
              <h4 className="notice-appeal__section-title">Business Documents Needed</h4>
              <ul className="notice-appeal__list">
                {guide.documents_needed.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>
          )}

          {guide.common_grounds.length > 0 && (
            <div className="notice-appeal__section">
              <h4 className="notice-appeal__section-title">Common Grounds for Appeal</h4>
              <ul className="notice-appeal__list">
                {guide.common_grounds.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          )}

          {guide.success_factors.length > 0 && (
            <div className="notice-appeal__section">
              <h4 className="notice-appeal__section-title">Success Factors</h4>
              <ul className="notice-appeal__list">
                {guide.success_factors.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {guide.notes.length > 0 && (
            <div className="notice-appeal__section">
              <h4 className="notice-appeal__section-title">Notes</h4>
              <ul className="notice-appeal__list">
                {guide.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

// ─── Notice Result ──────────────────────────────────────────────────────────

function NoticeResultView({ result }: { result: NoticeAnalysisResponse }) {
  const amountRows = [
    result.taxpayer_name ? { key: "Business Name", value: result.taxpayer_name } : null,
    result.taxpayer_ntn ? { key: "Company NTN", value: <span className="mono">{result.taxpayer_ntn}</span> } : null,
    result.notice_id ? { key: "Notice ID", value: <span className="mono">{result.notice_id}</span> } : null,
    result.issue_date ? { key: "Issue Date", value: formatDate(result.issue_date) } : null,
    result.deadline_date ? { key: "Deadline", value: formatDate(result.deadline_date) } : null,
    result.days_remaining != null
      ? {
          key: "Days Remaining",
          value: result.days_remaining > 0
            ? <Tag variant="warn">{result.days_remaining} days</Tag>
            : result.days_remaining === 0
            ? <Tag variant="err">Due today</Tag>
            : <Tag variant="err">{Math.abs(result.days_remaining)} days overdue</Tag>,
        }
      : null,
    result.total_demanded != null
      ? { key: "Total Demanded", value: <strong style={{ color: "var(--c-err)" }}>{formatPkr(result.total_demanded)}</strong> }
      : null,
    result.tax_amount != null
      ? { key: "Tax Amount", value: formatPkr(result.tax_amount) }
      : null,
    result.penalty_amount != null
      ? { key: "Penalty", value: formatPkr(result.penalty_amount) }
      : null,
    result.tax_years.length > 0
      ? { key: "Tax Years", value: result.tax_years.join(", ") }
      : null,
    result.sections_cited.length > 0
      ? { key: "Sections Cited", value: result.sections_cited.map((s) => (
          <Tag key={s} variant="accent">{s}</Tag>
        )) }
      : null,
    { key: "Confidence", value: <Tag variant={confidenceVariant(result.confidence)}>{Math.round(result.confidence * 100)}%</Tag> },
    { key: "Urgency", value: <Tag variant={urgencyVariant(result.urgency_level)}>{result.urgency_level}</Tag> },
  ].filter(Boolean) as Array<{ key: string; value: React.ReactNode }>;

  return (
    <div className="notice-result" data-testid="biz-result">
      {/* Header badges */}
      <div className="notice-result__badges">
        <Tag variant="accent">{result.notice_type || "Business Notice"}</Tag>
        {result.is_critical ? <Tag variant="err">Critical</Tag> : null}
        {result.is_appealable ? <Tag variant="warn">Appealable</Tag> : null}
        <span className="notice-result__analysis-id small muted">
          ID: {result.analysis_id}
        </span>
      </div>

      {/* Summary */}
      {result.summary && (
        <div className="notice-result__summary">
          <p>{result.summary}</p>
        </div>
      )}

      {/* Key details */}
      <Card title="Extracted Business Information" testId="biz-info-card">
        <Kv rows={amountRows} testId="biz-kv" />
      </Card>

      {/* Deadline urgency */}
      {result.deadline_date && (
        <Card
          title="Deadline Status"
          testId="biz-deadline-card"
        >
          <div className="notice-deadline">
            <div className="notice-deadline__date">
              <span className="notice-deadline__label">Deadline</span>
              <span className="notice-deadline__value">{formatDate(result.deadline_date)}</span>
            </div>
            {result.days_remaining != null && (
              <div
                className="notice-deadline__urgency"
                style={{ color: result.days_remaining <= 7 ? "var(--c-err)" : result.days_remaining <= 30 ? "var(--c-warn)" : "var(--c-ok)" }}
                data-testid="biz-deadline-urgency"
              >
                {result.days_remaining > 0
                  ? `${result.days_remaining} days remaining`
                  : result.days_remaining === 0
                  ? "Deadline is today!"
                  : `${Math.abs(result.days_remaining)} days overdue`}
              </div>
            )}
            <Tag variant={urgencyVariant(result.urgency_level)}>{result.urgency_level} urgency</Tag>
          </div>
        </Card>
      )}

      {/* Action Plan */}
      {result.action_plan && (
        <ActionPlanView plan={result.action_plan} />
      )}

      {/* Appeal Guide */}
      {result.appeal_guide && (
        <AppealGuideView guide={result.appeal_guide} />
      )}

      {/* Formatted text */}
      {result.formatted_text && (
        <CollapsibleText
          title="Full Formatted Text"
          text={result.formatted_text}
          initiallyOpen={false}
        />
      )}
    </div>
  );
}

// ─── History Item ───────────────────────────────────────────────────────────

interface HistoryItem {
  id: string;
  result: NoticeAnalysisResponse;
  ts: number;
  preview: string;
}

function HistoryItem({ item, onView }: {
  item: HistoryItem;
  onView: (id: string) => void;
}) {
  const shortPreview = item.preview.length > 120
    ? item.preview.slice(0, 120) + "…"
    : item.preview;

  return (
    <div
      className="notice-history__item"
      data-testid={`biz-history-item-${item.id}`}
    >
      <div className="notice-history__item-head">
        <Tag variant="accent">{item.result.notice_type || "Business Notice"}</Tag>
        {item.result.is_critical ? <Tag variant="err">Critical</Tag> : null}
        {item.result.deadline_date && (
          <span className="notice-history__item-date">
            Due: {formatDate(item.result.deadline_date)}
          </span>
        )}
        <span className="notice-history__item-ts small muted">
          {new Date(item.ts).toLocaleTimeString("en-PK", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
      <p className="notice-history__item-preview">{shortPreview}</p>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onView(item.id)}
        data-testid={`biz-history-view-${item.id}`}
      >
        View full analysis
      </Button>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function BusinessNoticesPage() {
  const { show: notify } = useNotification();

  const [noticeText, setNoticeText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NoticeAnalysisResponse | null>(null);

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [, setActiveHistoryId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showTypes, setShowTypes] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);

  const analyze = useCallback(async () => {
    setTextError(null);
    setError(null);

    if (!noticeText.trim()) {
      setTextError("Please paste the text of an FBR business notice before analyzing.");
      return;
    }
    if (noticeText.trim().length < 20) {
      setTextError("Notice text is too short. Please paste a more complete notice.");
      return;
    }

    setAnalyzing(true);
    try {
      const resp = await api.notices.analyze(noticeText.trim());
      setResult(resp);

      const newItem: HistoryItem = {
        id: resp.analysis_id || String(Date.now()),
        result: resp,
        ts: Date.now(),
        preview: resp.summary || noticeText.slice(0, 120),
      };
      setHistory((prev) => [newItem, ...prev.slice(0, 19)]);
      setActiveHistoryId(newItem.id);
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Cannot reach the server. Is the backend running?");
        notify("err", "Cannot reach the backend server.");
      } else if (err instanceof ApiError) {
        const msg = `Analysis failed: ${err.detail}`;
        setError(msg);
        notify("err", msg);
      } else {
        setError("An unexpected error occurred during analysis.");
        notify("err", "Unexpected error during business notice analysis.");
      }
    } finally {
      setAnalyzing(false);
    }
  }, [noticeText, notify]);

  const clear = useCallback(() => {
    setNoticeText("");
    setResult(null);
    setError(null);
    setTextError(null);
    setActiveHistoryId(null);
  }, []);

  const handleViewHistory = useCallback((id: string) => {
    const item = history.find((h) => h.id === id);
    if (item) {
      setResult(item.result);
      setActiveHistoryId(id);
      setShowHistory(false);
    }
  }, [history]);

  return (
    <ErrorBoundary>
      <section className="page page--notices">
        <header className="page__header">
          <div>
            <p className="page-eyebrow">Business · Notices</p>
            <h2 className="page__title">Business FBR Notices Analyzer</h2>
            <p className="page__subtitle">
              Paste an FBR notice for your business entity to get a structured analysis: extracted company details, action plan, appeal guide, and deadlines — powered by the live backend pipeline.
            </p>
          </div>
          <div className="page__header-actions">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowHistory((v) => !v)}
              data-testid="biz-history-toggle"
            >
              {showHistory ? "Hide" : "Show"} History ({history.length})
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowTypes((v) => !v)}
              data-testid="biz-types-toggle"
            >
              {showTypes ? "Hide" : "Show"} Business Notice Types
            </Button>
          </div>
        </header>

        <div className="page__content">
          {/* Notice types reference */}
          {showTypes && (
            <Card title="Supported Business Notice Types" testId="biz-types-card">
              <ul className="notice-types-list">
                {BUSINESS_NOTICE_TYPES_REFERENCE.map((t) => (
                  <li key={t} className="notice-types-list__item">{t}</li>
                ))}
              </ul>
            </Card>
          )}

          {/* Input form */}
          <Card
            title="Analyze a Business Notice"
            subtitle="Paste the full or partial text of an FBR notice addressed to your business, company, or AOP below"
            testId="biz-analyze-card"
          >
            <div className="notice-input">
              <Field
                label="Notice Text"
                error={textError ?? undefined}
                data-testid="biz-text-field"
              >
                <textarea
                  className="notice-input__textarea"
                  value={noticeText}
                  onChange={(e) => {
                    setNoticeText(e.target.value);
                    setTextError(null);
                  }}
                  placeholder="Paste the text of an FBR business notice here. Include the notice number, dates, company NTN, tax years, sales tax amounts, and sections cited…"
                  rows={8}
                  disabled={analyzing}
                  data-testid="biz-text-input"
                />
              </Field>

              <div className="notice-input__meta">
                <span className="small muted">
                  {noticeText.length} characters
                </span>
              </div>

              <div className="notice-input__actions">
                <Button
                  variant="primary"
                  loading={analyzing}
                  disabled={analyzing}
                  onClick={() => void analyze()}
                  data-testid="biz-analyze-button"
                >
                  {analyzing ? "Analyzing…" : "Analyze Notice"}
                </Button>
                <Button
                  variant="ghost"
                  disabled={analyzing}
                  onClick={clear}
                  data-testid="biz-clear-button"
                >
                  Clear
                </Button>
              </div>
            </div>
          </Card>

          {/* Loading */}
          {analyzing && (
            <Loading
              label="Analyzing business notice… Extracting company information, generating action plan and appeal guide."
              testId="biz-analyzing"
            />
          )}

          {/* Error */}
          {error ? (
            <StatusBanner
              kind="err"
              title="Analysis failed"
              description={error}
              testId="biz-error"
            />
          ) : null}

          {/* Result */}
          {result && !analyzing && (
            <NoticeResultView result={result} />
          )}

          {/* History */}
          {showHistory && history.length > 0 && (
            <Card title={`Business Notice Analysis History (${history.length})`} testId="biz-history-card">
              <div className="notice-history">
                {history.map((item) => (
                  <HistoryItem
                    key={item.id}
                    item={item}
                    onView={handleViewHistory}
                  />
                ))}
              </div>
            </Card>
          )}

          {showHistory && history.length === 0 && (
            <StatusBanner
              kind="info"
              title="No analysis history"
              description="Analyze your first FBR business notice to see it here."
              testId="biz-history-empty"
            />
          )}

          {/* Empty state */}
          {!result && !analyzing && !error && history.length === 0 && (
            <StatusBanner
              kind="info"
              title="Paste an FBR business notice to begin"
              description="Use the form above to paste notice text. The analysis pipeline will extract key company details, identify required documents, and provide a step-by-step action plan."
              testId="biz-empty-state"
            />
          )}
        </div>
      </section>

      <style>{`
        /* Notice input */
        .notice-input__textarea {
          width: 100%;
          padding: var(--s-4);
          border: 1px solid var(--c-line-strong);
          border-radius: var(--r-2);
          background: #fffaf0;
          font-family: var(--f-body);
          font-size: 14px;
          line-height: 1.6;
          resize: vertical;
          min-height: 180px;
        }

        .notice-input__textarea:focus {
          outline: 2px solid var(--c-accent);
          outline-offset: -1px;
          border-color: var(--c-accent);
        }

        .notice-input__meta {
          margin-top: var(--s-2);
          text-align: right;
        }

        .notice-input__actions {
          display: flex;
          gap: var(--s-3);
          margin-top: var(--s-4);
          align-items: center;
        }

        /* Result */
        .notice-result {
          display: flex;
          flex-direction: column;
          gap: var(--s-5);
        }

        .notice-result__badges {
          display: flex;
          align-items: center;
          gap: var(--s-2);
          flex-wrap: wrap;
        }

        .notice-result__analysis-id {
          margin-left: auto;
        }

        .notice-result__summary {
          font-size: 14px;
          line-height: 1.7;
          padding: var(--s-4);
          background: var(--c-accent-soft);
          border-left: 3px solid var(--c-accent);
          border-radius: var(--r-2);
        }

        /* Notice deadline */
        .notice-deadline {
          display: flex;
          align-items: center;
          gap: var(--s-5);
          flex-wrap: wrap;
        }

        .notice-deadline__date {
          display: flex;
          flex-direction: column;
        }

        .notice-deadline__label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--c-text-faint);
        }

        .notice-deadline__value {
          font-size: 16px;
          font-weight: 600;
        }

        .notice-deadline__urgency {
          font-size: 14px;
          font-weight: 700;
        }

        /* Action plan */
        .notice-plan__summary {
          font-size: 13.5px;
          line-height: 1.65;
          margin-bottom: var(--s-4);
          color: var(--c-text-muted);
        }

        .notice-steps {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: var(--s-4);
          counter-reset: steps;
        }

        .notice-step {
          padding: var(--s-4);
          background: var(--c-paper-2);
          border-radius: var(--r-2);
          border: 1px solid var(--c-line);
        }

        .notice-step__head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: var(--s-3);
          margin-bottom: var(--s-2);
          flex-wrap: wrap;
        }

        .notice-step__title {
          font-size: 14px;
        }

        .notice-step__badges {
          display: flex;
          gap: var(--s-2);
          flex-shrink: 0;
        }

        .notice-step__desc {
          font-size: 13.5px;
          line-height: 1.65;
          color: var(--c-text-muted);
          margin: 0 0 var(--s-3);
        }

        .notice-step__docs {
          font-size: 12.5px;
        }

        .notice-step__docs-label {
          font-weight: 600;
          color: var(--c-text);
          margin-right: var(--s-2);
        }

        .notice-step__docs ul {
          margin: var(--s-1) 0 0 var(--s-4);
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .notice-plan__tips {
          margin-top: var(--s-4);
          padding: var(--s-4);
          background: var(--c-paper-2);
          border-radius: var(--r-2);
        }

        .notice-plan__tips-title {
          font-size: 13px;
          font-weight: 700;
          margin-bottom: var(--s-2);
        }

        .notice-plan__tips ul {
          margin: 0;
          padding-left: var(--s-5);
          display: flex;
          flex-direction: column;
          gap: var(--s-1);
          font-size: 13px;
        }

        /* Appeal guide */
        .notice-appeal__section {
          margin-top: var(--s-4);
          padding-top: var(--s-4);
          border-top: 1px dashed var(--c-line);
        }

        .notice-appeal__section-title {
          font-size: 13px;
          font-weight: 700;
          margin-bottom: var(--s-2);
          color: var(--c-text);
        }

        .notice-appeal__list {
          margin: 0;
          padding-left: var(--s-5);
          display: flex;
          flex-direction: column;
          gap: var(--s-1);
          font-size: 13px;
        }

        /* Collapsible */
        .notice-collapse {
          background: #fffaf0;
          border: 1px solid var(--c-line);
          border-radius: var(--r-2);
          overflow: hidden;
        }

        .notice-collapse__toggle {
          width: 100%;
          text-align: left;
          background: var(--c-paper-2);
          border: 0;
          padding: var(--s-3) var(--s-5);
          font-size: 13.5px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: var(--s-2);
        }

        .notice-collapse__toggle:hover {
          background: var(--c-line);
        }

        .notice-collapse__body {
          padding: var(--s-4) var(--s-5);
          border-top: 1px solid var(--c-line);
        }

        .notice-collapse__text {
          font-family: var(--f-body);
          font-size: 13px;
          line-height: 1.7;
          white-space: pre-wrap;
          word-wrap: break-word;
          color: var(--c-text-muted);
          margin: 0;
        }

        /* History */
        .notice-history {
          display: flex;
          flex-direction: column;
          gap: var(--s-4);
        }

        .notice-history__item {
          padding: var(--s-4);
          background: var(--c-paper-2);
          border: 1px solid var(--c-line);
          border-radius: var(--r-2);
        }

        .notice-history__item-head {
          display: flex;
          align-items: center;
          gap: var(--s-2);
          flex-wrap: wrap;
          margin-bottom: var(--s-2);
        }

        .notice-history__item-date {
          font-size: 12px;
          color: var(--c-text-muted);
        }

        .notice-history__item-ts {
          margin-left: auto;
        }

        .notice-history__item-preview {
          font-size: 13px;
          color: var(--c-text-muted);
          line-height: 1.5;
          margin: 0 0 var(--s-3);
        }

        /* Notice types list */
        .notice-types-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: var(--s-2);
        }

        .notice-types-list__item {
          font-size: 13px;
          padding: var(--s-2) var(--s-3);
          background: var(--c-paper-2);
          border-radius: var(--r-2);
          border-left: 2px solid var(--c-accent);
        }

        /* Page header actions */
        .page__header-actions {
          display: flex;
          gap: var(--s-2);
          align-items: center;
        }
      `}</style>
    </ErrorBoundary>
  );
}