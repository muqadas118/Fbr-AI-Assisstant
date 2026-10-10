import { useState, useCallback, useEffect } from "react";
import clsx from "clsx";
import {
  api,
  ApiError,
  NetworkError,
  type CalendarDashboard,
  type CalendarEvent,
  type UpcomingTask,
} from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Loading } from "@/components/shell/Loading";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";
import { useWorkspace } from "@/state/workspace";

type TaxpayerType = "individual" | "business";

interface FilterState {
  priority: string;
  category: string;
}

function priorityVariant(p: string): "err" | "warn" | "accent" | "default" {
  switch (p) {
    case "critical": return "err";
    case "high": return "warn";
    case "medium": return "accent";
    default: return "default";
  }
}

function urgencyColor(urgency: string): string {
  switch (urgency) {
    case "critical": return "var(--c-err)";
    case "high": return "var(--c-warn)";
    default: return "var(--c-text)";
  }
}

function formatDate(iso: string): string {
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

// ─── Compliance Score Gauge ─────────────────────────────────────────────────

function ScoreGauge({ score, grade, color }: {
  score: number;
  grade: string;
  color: string;
}) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="cal-score" data-testid="cal-score-gauge">
      <div className="cal-score__ring">
        <svg viewBox="0 0 100 100" className="cal-score__svg">
          <circle cx="50" cy="50" r="40" fill="none" stroke="var(--c-line)" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${2 * Math.PI * 40}`}
            strokeDashoffset={`${2 * Math.PI * 40 * (1 - pct / 100)}`}
            transform="rotate(-90 50 50)"
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div className="cal-score__center">
          <span className="cal-score__number" style={{ color }}>{score}</span>
          <span className="cal-score__grade" style={{ color }}>{grade}</span>
        </div>
      </div>
      <p className="cal-score__label">Compliance Score</p>
    </div>
  );
}

// ─── Event Row ─────────────────────────────────────────────────────────────

function EventRow({
  event,
  onComplete,
}: {
  event: CalendarEvent;
  onComplete: (id: string) => void;
}) {
  const [reminding, setReminding] = useState(false);
  const [remindEmail, setRemindEmail] = useState("");
  const [showRemindForm, setShowRemindForm] = useState(false);
  const { show: notify } = useNotification();

  const handleRemind = useCallback(async () => {
    if (!remindEmail.trim()) return;
    setReminding(true);
    try {
      await api.calendar.scheduleReminder(event.id, remindEmail.trim(), ["email"]);
      setShowRemindForm(false);
      notify("ok", `Reminder scheduled for ${event.title}.`);
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Failed to schedule reminder: ${err.detail}`
        : err instanceof NetworkError
          ? "Network error — could not schedule the reminder."
          : "Failed to schedule the reminder.";
      notify("err", msg);
    } finally {
      setReminding(false);
    }
  }, [event.id, event.title, remindEmail, notify]);

  return (
    <div
      className={clsx(
        "cal-event",
        event.is_overdue && "cal-event--overdue",
        event.is_completed && "cal-event--completed",
      )}
      data-testid={`cal-event-${event.id}`}
    >
      <div className="cal-event__left">
        <div className="cal-event__title-row">
          <span className="cal-event__title">{event.title}</span>
          <Tag variant={priorityVariant(event.priority)}>{event.priority}</Tag>
          {event.is_overdue ? <Tag variant="err">Overdue</Tag> : null}
          {event.extension_available ? <Tag variant="accent">Extension Available</Tag> : null}
        </div>
        <div className="cal-event__meta">
          <span>{event.event_type}</span>
          <span className="cal-event__dot" aria-hidden>·</span>
          <span>{event.category}</span>
          {event.legal_reference ? (
            <>
              <span className="cal-event__dot" aria-hidden>·</span>
              <span className="mono">{event.legal_reference}</span>
            </>
          ) : null}
        </div>
        {event.description ? (
          <p className="cal-event__desc">{event.description}</p>
        ) : null}
        {event.penalty ? (
          <p className="cal-event__penalty">Penalty: {event.penalty}</p>
        ) : null}
      </div>

      <div className="cal-event__right">
        <div className="cal-event__date">
          <span className="cal-event__date-label">Due</span>
          <span className="cal-event__date-value">{formatDate(event.due_date)}</span>
        </div>
        <div
          className="cal-event__days"
          style={{ color: event.is_overdue ? "var(--c-err)" : urgencyColor(event.priority) }}
          data-testid={`cal-event-days-${event.id}`}
        >
          {event.days_remaining > 0
            ? `${event.days_remaining}d left`
            : event.days_remaining === 0
            ? "Due today"
            : `${Math.abs(event.days_remaining)}d overdue`}
        </div>
        <div className="cal-event__actions">
          {!event.is_completed && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onComplete(event.id)}
                data-testid={`cal-complete-${event.id}`}
              >
                Mark Complete
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowRemindForm((v) => !v)}
                data-testid={`cal-remind-btn-${event.id}`}
              >
                Remind
              </Button>
            </>
          )}
        </div>

        {showRemindForm && (
          <div className="cal-event__remind-form">
            <input
              type="email"
              className="cal-event__remind-input"
              placeholder="your@email.com"
              value={remindEmail}
              onChange={(e) => setRemindEmail(e.target.value)}
              aria-label="Reminder recipient email"
              data-testid={`cal-remind-email-${event.id}`}
            />
            <Button
              variant="primary"
              size="sm"
              loading={reminding}
              disabled={!remindEmail.trim()}
              onClick={handleRemind}
              data-testid={`cal-remind-submit-${event.id}`}
            >
              Schedule
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowRemindForm(false)}
              data-testid={`cal-remind-cancel-${event.id}`}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Upcoming Task Card ─────────────────────────────────────────────────────

function UpcomingTaskCard({ task }: { task: UpcomingTask }) {
  return (
    <div className="cal-task" data-testid={`cal-task-${task.event_id}`}>
      <div className="cal-task__header">
        <span className="cal-task__title">{task.title}</span>
        <Tag variant={priorityVariant(task.priority)}>{task.priority}</Tag>
        {task.is_overdue ? <Tag variant="err">Overdue</Tag> : null}
      </div>
      <div className="cal-task__meta">
        <span>{task.event_type}</span>
        <span>·</span>
        <span>{task.category}</span>
      </div>
      <div
        className="cal-task__urgency"
        style={{ color: task.is_overdue ? "var(--c-err)" : urgencyColor(task.urgency) }}
        data-testid={`cal-task-urgency-${task.event_id}`}
      >
        {task.urgency}
      </div>
      {task.action_required ? (
        <p className="cal-task__action">{task.action_required}</p>
      ) : null}
      <div className="cal-task__date">
        Due: {formatDate(task.due_date)}
        {task.days_remaining > 0
          ? ` (${task.days_remaining}d left)`
          : task.days_remaining === 0
          ? " (Due today)"
          : ` (${Math.abs(task.days_remaining)}d overdue)`}
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function CalendarPage() {
  const { show: notify } = useNotification();

  const [dashboard, setDashboard] = useState<CalendarDashboard | null>(null);
  const [allEvents, setAllEvents] = useState<CalendarEvent[]>([]);
  const [upcomingTasks, setUpcomingTasks] = useState<UpcomingTask[]>([]);
  const [overdueEvents, setOverdueEvents] = useState<CalendarEvent[]>([]);
  const [recommendations, setRecommendations] = useState<string[]>([]);

  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filter, setFilter] = useState<FilterState>({ priority: "", category: "" });

  // Taxpayer type mirrors the active workspace: Personal = Individual, Business = Business.
  const workspace = useWorkspace((s) => s.active);
  const taxpayerType: TaxpayerType = workspace === "business" ? "business" : "individual";

  // Derive filtered events from allEvents
  const filteredEvents = allEvents.filter((e) => {
    if (filter.priority && e.priority !== filter.priority) return false;
    if (filter.category && e.category !== filter.category) return false;
    return true;
  });

  // Extract unique categories and priorities
  const categories = Array.from(new Set(allEvents.map((e) => e.category).filter(Boolean)));
  const priorities = ["critical", "high", "medium", "low"];

  const fetchDashboard = useCallback(async () => {
    setLoadingDashboard(true);
    try {
      const data = await api.calendar.getDashboard(taxpayerType);
      setDashboard(data);
    } catch (err) {
      if (err instanceof NetworkError) {
        notify("err", "Cannot reach the server. Is the backend running?");
      } else if (err instanceof ApiError) {
        notify("err", `Failed to load dashboard: ${err.detail}`);
      }
    } finally {
      setLoadingDashboard(false);
    }
  }, [taxpayerType, notify]);

  const fetchEvents = useCallback(async () => {
    setLoadingEvents(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {
        taxpayer_type: taxpayerType,
        limit: 100,
      };
      if (filter.priority) params.priority = filter.priority;
      if (filter.category) params.category = filter.category;

      const [eventsResp, upcomingResp] = await Promise.all([
        api.calendar.get(params as Parameters<typeof api.calendar.get>[0]),
        api.calendar.getUpcoming(taxpayerType, 30),
      ]);

      setAllEvents(eventsResp.events ?? []);
      setOverdueEvents(eventsResp.overdue_events ?? []);
      setRecommendations(eventsResp.recommendations ?? []);
      setUpcomingTasks(upcomingResp ?? []);
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Cannot reach the server. Is the backend running?");
      } else if (err instanceof ApiError) {
        setError(`Failed to load events: ${err.detail}`);
      } else {
        setError("An unexpected error occurred while loading events.");
      }
    } finally {
      setLoadingEvents(false);
    }
  }, [taxpayerType, filter]);

  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  useEffect(() => {
    void fetchEvents();
  }, [fetchEvents]);

  const handleComplete = useCallback(async (eventId: string) => {
    try {
      await api.calendar.markComplete(eventId);
      notify("ok", "Event marked as complete.");
      setAllEvents((prev) => prev.filter((e) => e.id !== eventId));
      setOverdueEvents((prev) => prev.filter((e) => e.id !== eventId));
    } catch {
      notify("err", "Could not mark event as complete. Please try again.");
    }
  }, [notify]);

  const clearFilters = () => setFilter({ priority: "", category: "" });

  const hasActiveFilters = Boolean(filter.priority || filter.category);

  return (
    <ErrorBoundary>
      <section className="page page--calendar">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Calendar</div>
            <h2 className="page__title">Compliance Calendar</h2>
            <p className="page__subtitle">
              Your tax compliance deadlines, upcoming tasks, and overdue items — all powered by the live backend pipeline.
            </p>
          </div>
          <div className="page__header-actions">
            <div className="cal-taxpayer-chip" data-testid="cal-taxpayer-type" title="Taxpayer type follows your active workspace">
              <span className="cal-taxpayer-chip__label">Taxpayer Type</span>
              <span className="cal-taxpayer-chip__value" data-testid="cal-taxpayer-value">
                {taxpayerType === "business" ? "Business" : "Individual"}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void fetchDashboard()}
              data-testid="cal-refresh-btn"
            >
              Refresh
            </Button>
          </div>
        </header>

        <div className="page__content">
          {/* ── Dashboard ── */}
          {loadingDashboard ? (
            <div className="cal-dashboard-loading">
              <Loading label="Loading compliance dashboard…" testId="cal-dashboard-loading" />
            </div>
          ) : dashboard ? (
            <Card
              title="Compliance Dashboard"
              testId="cal-dashboard-card"
              className="cal-dashboard"
            >
              <div className="cal-dashboard__grid">
                <ScoreGauge
                  score={dashboard.compliance_score}
                  grade={dashboard.compliance_grade}
                  color={dashboard.compliance_grade_color || "var(--c-accent)"}
                />

                <div className="cal-dashboard__stats">
                  <Kv
                    rows={[
                      {
                        key: "Total Events",
                        value: <strong>{dashboard.total_events}</strong>,
                      },
                      {
                        key: "Overdue",
                        value: dashboard.overdue_count > 0
                          ? <Tag variant="err">{dashboard.overdue_count} overdue</Tag>
                          : <Tag variant="ok">None overdue</Tag>,
                      },
                      {
                        key: "Critical (30d)",
                        value: <Tag variant="err">{dashboard.critical_upcoming_30d}</Tag>,
                      },
                      {
                        key: "Critical (7d)",
                        value: <Tag variant="warn">{dashboard.critical_upcoming_7d}</Tag>,
                      },
                    ]}
                    testId="cal-dashboard-kv"
                  />
                </div>

                {dashboard.summary_message ? (
                  <div className="cal-dashboard__message">
                    <p>{dashboard.summary_message}</p>
                  </div>
                ) : null}
              </div>
            </Card>
          ) : null}

          {/* ── Error ── */}
          {error ? (
            <StatusBanner
              kind="err"
              title="Could not load events"
              description={error}
              testId="cal-error"
            />
          ) : null}

          {/* ── Filters ── */}
          <div className="cal-filters card" data-testid="cal-filters">
            <div className="cal-filters__row">
              <span className="cal-filters__label">Filter:</span>
              <Field label="Priority" data-testid="cal-filter-priority">
                <Select
                  value={filter.priority}
                  onChange={(v) => setFilter((f) => ({ ...f, priority: v }))}
                  testId="cal-priority-select"
                  ariaLabel="Priority filter"
                  options={[
                    { value: "", label: "All priorities" },
                    ...priorities.map((p) => ({ value: p, label: p.charAt(0).toUpperCase() + p.slice(1) })),
                  ]}
                />
              </Field>
              {categories.length > 0 && (
                <Field label="Category" data-testid="cal-filter-category">
                  <Select
                    value={filter.category}
                    onChange={(v) => setFilter((f) => ({ ...f, category: v }))}
                    testId="cal-category-select"
                    ariaLabel="Category filter"
                    options={[{ value: "", label: "All categories" }, ...categories]}
                  />
                </Field>
              )}
              {hasActiveFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearFilters}
                  data-testid="cal-clear-filters"
                >
                  Clear filters
                </Button>
              )}
            </div>
          </div>

          {/* ── Loading Events ── */}
          {!loadingDashboard && loadingEvents ? (
            <div className="cal-events-loading">
              <Loading
                label="Loading events…"
                testId="cal-events-loading"
              />
            </div>
          ) : (
            <>
              {/* ── Overdue Events ── */}
              {overdueEvents.length > 0 && (
                <section className="cal-section" data-testid="cal-overdue-section">
                  <div className="cal-section__head">
                    <h3 className="cal-section__title">
                      <Tag variant="err">{overdueEvents.length}</Tag>
                      {" "}Overdue
                    </h3>
                  </div>
                  <div className="cal-event-list">
                    {overdueEvents.map((e) => (
                      <EventRow
                        key={e.id}
                        event={e}
                        onComplete={handleComplete}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* ── Critical in next 7 days ── */}
              {(() => {
                const critical7 = allEvents.filter(
                  (e) => !e.is_overdue && e.days_remaining <= 7 && e.priority === "critical",
                );
                return critical7.length > 0 ? (
                  <section className="cal-section" data-testid="cal-critical-section">
                    <div className="cal-section__head">
                      <h3 className="cal-section__title">
                        <Tag variant="warn">{critical7.length}</Tag>
                        {" "}Critical (next 7 days)
                      </h3>
                    </div>
                    <div className="cal-event-list">
                      {critical7.map((e) => (
                        <EventRow
                          key={e.id}
                          event={e}
                          onComplete={handleComplete}
                          />
                      ))}
                    </div>
                  </section>
                ) : null;
              })()}

              {/* ── Upcoming Tasks ── */}
              {upcomingTasks.length > 0 && (
                <section className="cal-section" data-testid="cal-upcoming-section">
                  <div className="cal-section__head">
                    <h3 className="cal-section__title">Upcoming Tasks</h3>
                    <span className="cal-section__meta">{upcomingTasks.length} tasks</span>
                  </div>
                  <div className="cal-task-grid">
                    {upcomingTasks.map((t) => (
                      <UpcomingTaskCard key={t.event_id} task={t} />
                    ))}
                  </div>
                </section>
              )}

              {/* ── All Events (filtered) ── */}
              {filteredEvents.length > 0 ? (
                <section className="cal-section" data-testid="cal-events-section">
                  <div className="cal-section__head">
                    <h3 className="cal-section__title">
                      All Events
                      {hasActiveFilters ? ` (${filteredEvents.length} of ${allEvents.length})` : ` (${filteredEvents.length})`}
                    </h3>
                  </div>
                  <div className="cal-event-list">
                    {filteredEvents.map((e) => (
                      <EventRow
                        key={e.id}
                        event={e}
                        onComplete={handleComplete}
                      />
                    ))}
                  </div>
                </section>
              ) : !loadingEvents && !error ? (
                <StatusBanner
                  kind="info"
                  title="No events found"
                  description={hasActiveFilters
                    ? "No events match the current filters. Try clearing the filters."
                    : "No compliance events are available for your profile. Check back later or update your taxpayer type."}
                  testId="cal-empty"
                />
              ) : null}

              {/* ── Recommendations ── */}
              {recommendations.length > 0 && (
                <Card title="Recommendations" testId="cal-recommendations">
                  <ul className="cal-recommendations">
                    {recommendations.map((rec, i) => (
                      <li key={i} className="cal-recommendations__item" data-testid={`cal-rec-${i}`}>
                        {rec}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          )}
        </div>
      </section>

      
    </ErrorBoundary>
  );
}
