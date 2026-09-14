import { useState, useCallback, useEffect } from "react";
import clsx from "clsx";
import { api, ApiError, NetworkError } from "@/lib/api";
import { Loading } from "@/components/shell/Loading";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Field } from "@/components/ui/Field";
import { useNotification } from "@/state/notifications";
import { useAuth } from "@/state/auth";
import type { MonitorEvent, MonitorDashboard } from "@/lib/api";

type TabId = "all" | "unread" | "critical" | "acknowledged";

const TABS: { id: TabId; label: string }[] = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "critical", label: "Critical" },
  { id: "acknowledged", label: "Acknowledged" },
];

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function severityVariant(sev: string): "err" | "warn" | "accent" | "default" {
  if (sev === "critical") return "err";
  if (sev === "high") return "warn";
  if (sev === "medium") return "accent";
  return "default";
}

function eventIcon(type: string): string {
  const t = type?.toLowerCase() ?? "";
  if (t.includes("notice")) return "document-text";
  if (t.includes("filing") || t.includes("return")) return "calendar";
  if (t.includes("payment")) return "bank";
  if (t.includes("penalty") || t.includes("fine")) return "alert";
  if (t.includes("deadline")) return "clock";
  if (t.includes("verification") || t.includes("ntn") || t.includes("filer")) return "badge";
  if (t.includes("invoice") || t.includes("itc")) return "receipt";
  return "bell";
}

function InboxItemIcon({ type }: { type: string }) {
  const ico = eventIcon(type);
  return (
    <div className="inbox__item-icon" aria-hidden>
      {ico === "document-text" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
        </svg>
      )}
      {ico === "calendar" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
        </svg>
      )}
      {ico === "bank" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="22" x2="21" y2="22" /><line x1="6" y1="18" x2="6" y2="11" /><line x1="10" y1="18" x2="10" y2="11" /><line x1="14" y1="18" x2="14" y2="11" /><line x1="18" y1="18" x2="18" y2="11" /><polygon points="12 2 20 7 4 7" />
        </svg>
      )}
      {ico === "alert" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      )}
      {ico === "clock" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
        </svg>
      )}
      {ico === "badge" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
        </svg>
      )}
      {ico === "receipt" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 6 2 18 2 18 9" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" />
        </svg>
      )}
      {ico === "bell" && (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      )}
    </div>
  );
}

interface InboxItemProps {
  event: MonitorEvent;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string) => void;
  onMarkRead: (id: string) => void;
  acknowledging: boolean;
  resolving: boolean;
}

function InboxItem({ event, onAcknowledge, onResolve, onMarkRead, acknowledging, resolving }: InboxItemProps) {
  const [expanded, setExpanded] = useState(false);

  const detectedAt = event.detected_at
    ? new Date(event.detected_at).toLocaleDateString("en-PK", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const isRead = event.status === "acknowledged" || event.status === "resolved";
  const isResolved = event.status === "resolved";

  return (
    <article
      className={clsx(
        "inbox__item",
        !isRead && "inbox__item--unread",
        isResolved && "inbox__item--resolved",
        expanded && "inbox__item--expanded",
      )}
      data-testid={`biz-item-${event.id}`}
      aria-expanded={expanded}
    >
      <button
        type="button"
        className="inbox__item-header"
        onClick={() => setExpanded((e) => !e)}
        aria-label={`${expanded ? "Collapse" : "Expand"} event: ${event.title}`}
      >
        <InboxItemIcon type={event.type} />
        <div className="inbox__item-body">
          <div className="inbox__item-top">
            <span className="inbox__item-title">{event.title}</span>
            <div className="inbox__item-badges">
              <Tag variant={severityVariant(event.severity)} className="inbox__severity">
                {event.severity}
              </Tag>
              {event.requires_action && (
                <Tag variant="warn" className="inbox__action-badge">Action Required</Tag>
              )}
            </div>
          </div>
          <p className="inbox__item-desc">{event.description}</p>
          <div className="inbox__item-meta">
            <span className="inbox__item-type">{event.type}</span>
            <span className="inbox__item-time">{detectedAt}</span>
          </div>
        </div>
        <div className="inbox__item-chevron" aria-hidden>
          {expanded ? (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="18 15 12 9 6 15" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          )}
        </div>
      </button>

      {expanded && (
        <div className="inbox__item-details" data-testid={`biz-details-${event.id}`}>
          {event.reference_number && (
            <div className="inbox__detail-row">
              <span className="inbox__detail-label">Reference</span>
              <span className="inbox__detail-value inbox__detail-value--mono">{event.reference_number}</span>
            </div>
          )}
          {event.action_deadline && (
            <div className="inbox__detail-row">
              <span className="inbox__detail-label">Deadline</span>
              <span className="inbox__detail-value">
                {new Date(event.action_deadline).toLocaleDateString("en-PK", {
                  day: "numeric", month: "long", year: "numeric",
                })}
              </span>
            </div>
          )}
          <div className="inbox__detail-row">
            <span className="inbox__detail-label">Status</span>
            <Tag
              variant={
                event.status === "resolved" ? "ok" :
                event.status === "acknowledged" ? "accent" : "default"
              }
            >
              {event.status}
            </Tag>
          </div>
          <div className="inbox__actions">
            {!isRead && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onMarkRead(event.id)}
                data-testid={`biz-mark-read-${event.id}`}
              >
                Mark as Read
              </Button>
            )}
            {!isRead && (
              <Button
                variant="secondary"
                size="sm"
                loading={acknowledging}
                onClick={() => onAcknowledge(event.id)}
                data-testid={`biz-ack-${event.id}`}
              >
                Acknowledge
              </Button>
            )}
            {!isResolved && (
              <Button
                variant="primary"
                size="sm"
                loading={resolving}
                onClick={() => onResolve(event.id)}
                data-testid={`biz-resolve-${event.id}`}
              >
                Resolve
              </Button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

export function BusinessMonitorPage() {
  // session-derived id with manual override
  const sessionId = useAuth((s) => s.user?.id ?? "");
  const { show: notify } = useNotification();
  const [userId, setUserId] = useState("");
  const [userIdInput, setUserIdInput] = useState("");
  useEffect(() => {
    if (sessionId && !userId) {
      setUserId(sessionId);
      setUserIdInput(sessionId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
  const [dashboard, setDashboard] = useState<MonitorDashboard | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("all");
  const [loadingStats, setLoadingStats] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const fetchDashboard = useCallback(async (uid: string) => {
    if (!uid.trim()) return;
    setLoadingStats(true);
    setError(null);
    try {
      const data = await api.monitor.getDashboard(uid.trim());
      setDashboard(data);
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Network error — could not reach the server. Please check your connection.");
      } else if (err instanceof ApiError) {
        setError(`API error (${err.status}): ${err.detail}`);
      } else {
        setError("An unexpected error occurred while loading the compliance monitor.");
      }
      setDashboard(null);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  const handleLoadDashboard = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    setUserId(userIdInput.trim());
    void fetchDashboard(userIdInput.trim());
  }, [userIdInput, fetchDashboard]);

  useEffect(() => {
    if (userId) {
      void fetchDashboard(userId);
    }
  }, [userId, fetchDashboard]);

  const handleAcknowledge = useCallback(async (eventId: string) => {
    setAcknowledgingId(eventId);
    try {
      await api.monitor.acknowledgeEvent(eventId);
      notify("ok", "Event acknowledged");
      void fetchDashboard(userId);
    } catch {
      notify("err", "Failed to acknowledge event");
    } finally {
      setAcknowledgingId(null);
    }
  }, [userId, fetchDashboard, notify]);

  const handleResolve = useCallback(async (eventId: string) => {
    setResolvingId(eventId);
    try {
      await api.monitor.resolveEvent(eventId);
      notify("ok", "Event resolved");
      void fetchDashboard(userId);
    } catch {
      notify("err", "Failed to resolve event");
    } finally {
      setResolvingId(null);
    }
  }, [userId, fetchDashboard, notify]);

  const handleMarkRead = useCallback(async (eventId: string) => {
    void handleAcknowledge(eventId);
  }, [handleAcknowledge]);

  const filteredEvents = dashboard?.recent_events
    ? [...dashboard.recent_events].sort((a, b) => {
        const diff = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
        if (diff !== 0) return diff;
        return new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime();
      }).filter((ev) => {
        if (activeTab === "unread") return ev.status === "new" || ev.status === "unread";
        if (activeTab === "critical") return ev.severity === "critical";
        if (activeTab === "acknowledged") return ev.status === "acknowledged" || ev.status === "resolved";
        return true;
      })
    : [];

  return (
    <ErrorBoundary>
      <section className="page page--inbox" data-testid="biz-monitor">
        <header className="page__header">
          <div>
            <p className="page-eyebrow">Business · Monitor</p>
            <h2 className="page__title">Business Compliance Monitor</h2>
            <p className="page__subtitle">
              Filing deadlines, sales tax returns, withholding payments, refunds and audit risks for your company.
            </p>
          </div>
        </header>

        <div className="page__content">
          {/* User ID setup */}
          <Card className="inbox__setup" testId="biz-monitor-setup">
            <form onSubmit={handleLoadDashboard} className="inbox__setup-form" data-testid="biz-monitor-setup-form">
              <Field
                label="User ID"
                helperText="Enter your user ID to load business compliance events from the monitor dashboard."
              >
                <input
                  type="text"
                  className="field__input"
                  value={userIdInput}
                  onChange={(e) => setUserIdInput(e.target.value)}
                  placeholder="e.g. biz-12345"
                  data-testid="biz-user-id-input"
                  aria-label="User ID for business compliance monitor"
                />
              </Field>
              <Button type="submit" variant="primary" disabled={!userIdInput.trim() || loadingStats}>
                {loadingStats ? "Loading…" : "Load Monitor"}
              </Button>
            </form>
          </Card>

          {error && (
            <StatusBanner
              kind="err"
              title="Failed to load monitor"
              description={error}
              className="inbox__error"
              testId="biz-monitor-error"
            />
          )}

          {loadingStats && !dashboard && (
            <Loading label="Fetching compliance data…" fullscreen={false} testId="biz-monitor-loading" />
          )}

          {dashboard && !loadingStats && (
            <>
              {/* Quick stats */}
              <div className="inbox__stats" data-testid="biz-monitor-stats">
                <div className="inbox__stat">
                  <span className="inbox__stat-value">{dashboard.unread_count}</span>
                  <span className="inbox__stat-label">Unread</span>
                </div>
                <div className="inbox__stat inbox__stat--critical">
                  <span className="inbox__stat-value">{dashboard.critical_count}</span>
                  <span className="inbox__stat-label">Critical</span>
                </div>
                <div className="inbox__stat inbox__stat--action">
                  <span className="inbox__stat-value">{dashboard.action_required}</span>
                  <span className="inbox__stat-label">Action Required</span>
                </div>
                <div className="inbox__stat">
                  <span className="inbox__stat-value">{dashboard.total_events}</span>
                  <span className="inbox__stat-label">Total Events</span>
                </div>
              </div>

              {/* Tabs */}
              <div className="inbox__tabs" role="tablist" aria-label="Compliance filters" data-testid="biz-monitor-tabs">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab.id}
                    className={clsx("inbox__tab", activeTab === tab.id && "inbox__tab--active")}
                    onClick={() => setActiveTab(tab.id)}
                    data-testid={`biz-monitor-tab-${tab.id}`}
                  >
                    {tab.label}
                    {dashboard && tab.id === "critical" && dashboard.critical_count > 0 && (
                      <span className="inbox__tab-badge">{dashboard.critical_count}</span>
                    )}
                    {dashboard && tab.id === "unread" && dashboard.unread_count > 0 && (
                      <span className="inbox__tab-badge">{dashboard.unread_count}</span>
                    )}
                  </button>
                ))}
              </div>

              {/* Monitor list */}
              <div
                className="inbox__list"
                role="tabpanel"
                aria-label={`${activeTab} events`}
                data-testid="biz-monitor-list"
              >
                {filteredEvents.length === 0 ? (
                  <div className="inbox__empty" data-testid="biz-monitor-empty">
                    <div className="inbox__empty-icon" aria-hidden>
                      <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                      </svg>
                    </div>
                    <p className="inbox__empty-title">No compliance events</p>
                    <p className="inbox__empty-sub">
                      {activeTab === "all"
                        ? "Your compliance monitor is clear. No filing or payment events detected."
                        : `No ${activeTab} events to show.`}
                    </p>
                  </div>
                ) : (
                  filteredEvents.map((event) => (
                    <InboxItem
                      key={event.id}
                      event={event}
                      onAcknowledge={handleAcknowledge}
                      onResolve={handleResolve}
                      onMarkRead={handleMarkRead}
                      acknowledging={acknowledgingId === event.id}
                      resolving={resolvingId === event.id}
                    />
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </section>
    </ErrorBoundary>
  );
}