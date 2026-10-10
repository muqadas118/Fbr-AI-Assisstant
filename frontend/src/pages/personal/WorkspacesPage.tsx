import { useState, useCallback, useEffect } from "react";
import clsx from "clsx";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError, NetworkError } from "@/lib/api";
import { Loading } from "@/components/shell/Loading";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Field } from "@/components/ui/Field";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";
import { useAuth } from "@/state/auth";
import type { Team, CalendarDashboard, UpcomingTask } from "@/lib/api";

interface Workspace {
  id: string;
  name: string;
  type: "personal" | "business";
  ntn?: string;
  memberCount: number;
  createdDate: string;
  isActive: boolean;
  ownerId?: string;
  plan?: string;
}

interface WorkspaceForm {
  name: string;
  type: "personal" | "business";
  ntn: string;
}

const EMPTY_FORM: WorkspaceForm = {
  name: "",
  type: "personal",
  ntn: "",
};

function WorkspaceIcon({ type }: { type: "personal" | "business" }) {
  if (type === "business") {
    return (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function ComplianceBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return <Tag variant="default">No Data</Tag>;
  }
  if (score >= 80) return <Tag variant="ok">{score} / 100 — Excellent</Tag>;
  if (score >= 60) return <Tag variant="accent">{score} / 100 — Good</Tag>;
  if (score >= 40) return <Tag variant="warn">{score} / 100 — Fair</Tag>;
  return <Tag variant="err">{score} / 100 — Needs Attention</Tag>;
}

function WorkspaceCard({
  workspace,
  isActive,
  onSelect,
}: {
  workspace: Workspace;
  isActive: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      className={clsx("ws__card", isActive && "ws__card--active")}
      onClick={() => onSelect(workspace.id)}
      data-testid={`ws-card-${workspace.id}`}
      aria-pressed={isActive}
      aria-label={`Select workspace: ${workspace.name}`}
    >
      {isActive && (
        <div className="ws__card-active-bar" aria-hidden />
      )}
      <div className="ws__card-icon">
        <WorkspaceIcon type={workspace.type} />
      </div>
      <div className="ws__card-body">
        <div className="ws__card-top">
          <span className="ws__card-name">{workspace.name}</span>
          <Tag variant={workspace.type === "personal" ? "accent" : "default"}>
            {workspace.type}
          </Tag>
        </div>
        {workspace.ntn && (
          <code className="ws__card-ntn">{workspace.ntn}</code>
        )}
        <div className="ws__card-meta">
          <span className="ws__card-members">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            {workspace.memberCount} member{workspace.memberCount !== 1 ? "s" : ""}
          </span>
          <span className="ws__card-date">
            {new Date(workspace.createdDate).toLocaleDateString("en-PK", {
              day: "numeric", month: "short", year: "numeric",
            })}
          </span>
        </div>
        {workspace.plan && (
          <span className="ws__card-plan">{workspace.plan} plan</span>
        )}
      </div>
      {isActive && (
        <div className="ws__card-active-badge" aria-label="Active workspace">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
      )}
    </button>
  );
}

function QuickLinkCard({
  label,
  icon,
  to,
}: {
  label: string;
  icon: React.ReactNode;
  to: string;
}) {
  return (
    <Link
      className="ws__quick-link"
      to={to}
      data-testid={`ws-quicklink-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="ws__quick-link-icon" aria-hidden>{icon}</div>
      <span className="ws__quick-link-label">{label}</span>
    </Link>
  );
}

/** Route prefix for the workspace the hub is currently mounted in. */
function useWorkspaceBasePath(): string {
  const location = useLocation();
  return location.pathname.startsWith("/business") ? "/business" : "/personal";
}

export function WorkspacesPage() {
  // session-derived id with manual override
  const sessionId = useAuth((s) => s.user?.id ?? "");
  const basePath = useWorkspaceBasePath();
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
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [calendarDashboard, setCalendarDashboard] = useState<CalendarDashboard | null>(null);
  const [upcomingTasks, setUpcomingTasks] = useState<UpcomingTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingCalendar, setLoadingCalendar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState<WorkspaceForm>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof WorkspaceForm, string>>>({});
  const [creating, setCreating] = useState(false);
  const [pendingInvitationCount, setPendingInvitationCount] = useState(0);

  const fetchWorkspaces = useCallback(async (uid: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.workspaces.get(uid.trim());
      const wsList: Workspace[] = (data.workspaces ?? []).map((t: Team) => ({
        id: t.id,
        name: t.name,
        type: t.organization_type === "business" ? "business" : "personal",
        ntn: t.ntn,
        memberCount: t.member_count,
        createdDate: t.created_at,
        isActive: t.is_active,
        ownerId: t.owner_id,
        plan: t.plan,
      }));
      setWorkspaces(wsList);
      // Set first workspace as active by default if none selected
      if (wsList.length > 0 && !activeWorkspaceId) {
        const active = wsList.find((w) => w.isActive) ?? wsList[0];
        setActiveWorkspaceId(active.id);
      }
      // Real pending-invitation count for this user (was a hard-coded 0).
      try {
        const dash = await api.team.getUserDashboard(uid.trim());
        setPendingInvitationCount(dash.pending_invitations?.length ?? 0);
      } catch {
        // non-critical — the stat card degrades to 0
        setPendingInvitationCount(0);
      }
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Network error — could not load workspaces.");
      } else if (err instanceof ApiError) {
        setError(`API error (${err.status}): ${err.detail}`);
      } else {
        setError("An unexpected error occurred while loading workspaces.");
      }
      setWorkspaces([]);
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId]);

  const fetchCalendarData = useCallback(async (taxpayerType: string) => {
    setLoadingCalendar(true);
    try {
      const [dash, upcoming] = await Promise.allSettled([
        api.calendar.getDashboard(taxpayerType),
        api.calendar.getUpcoming(taxpayerType, 14),
      ]);
      if (dash.status === "fulfilled") setCalendarDashboard(dash.value);
      if (upcoming.status === "fulfilled") setUpcomingTasks(upcoming.value);
    } catch {
      // non-critical
    } finally {
      setLoadingCalendar(false);
    }
  }, []);

  const handleLoad = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const uid = userIdInput.trim();
    setUserId(uid);
    void fetchWorkspaces(uid);
    void fetchCalendarData("individual");
  }, [userIdInput, fetchWorkspaces, fetchCalendarData]);

  const handleSwitchWorkspace = useCallback((id: string) => {
    setActiveWorkspaceId(id);
    const ws = workspaces.find((w) => w.id === id);
    if (ws) {
      notify("info", `Switched to workspace: ${ws.name}`);
      void fetchCalendarData(ws.type === "business" ? "business" : "individual");
    }
  }, [workspaces, notify, fetchCalendarData]);

  const validateCreateForm = useCallback((): boolean => {
    const errs: Partial<Record<keyof WorkspaceForm, string>> = {};
    if (!createForm.name.trim()) errs.name = "Workspace name is required.";
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  }, [createForm]);

  const handleCreate = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateCreateForm()) return;
    if (!userId.trim()) {
      notify("err", "Load your user ID above before creating a workspace.");
      return;
    }
    setCreating(true);
    try {
      // Real workspace creation — POST /workspaces/create (a team under the hood).
      const created = await api.workspaces.createWorkspace({
        user_id: userId.trim(),
        name: createForm.name.trim(),
        workspace_type: createForm.type,
        ntn: createForm.ntn.trim() || undefined,
      });
      notify("ok", `Workspace "${created.name}" created successfully.`);
      setCreateForm(EMPTY_FORM);
      setFormErrors({});
      setShowCreateForm(false);
      void fetchWorkspaces(userId.trim());
    } catch (err) {
      if (err instanceof ApiError) {
        notify("err", `Failed to create workspace: ${err.detail}`);
      } else if (err instanceof NetworkError) {
        notify("err", "Network error — could not create workspace.");
      } else {
        notify("err", "An unexpected error occurred.");
      }
    } finally {
      setCreating(false);
    }
  }, [createForm, validateCreateForm, userId, fetchWorkspaces, notify]);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId);
  const pendingInvitations = pendingInvitationCount;
  const totalMembers = workspaces.reduce((sum, w) => sum + w.memberCount, 0);

  return (
    <ErrorBoundary>
      <section className="page page--workspaces">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Workspaces</div>
            <h2 className="page__title">My Workspaces</h2>
            <p className="page__subtitle">
              Manage your personal and business workspaces, compliance status, and team.
            </p>
          </div>
        </header>

        <div className="page__content">
          {/* User ID setup */}
          <Card className="ws__setup" testId="ws-setup">
            <form onSubmit={handleLoad} className="ws__setup-form" data-testid="ws-setup-form">
              <Field
                label="User ID"
                helperText="Enter your user ID to load your workspaces."
              >
                <input
                  type="text"
                  className="field__input"
                  value={userIdInput}
                  onChange={(e) => setUserIdInput(e.target.value)}
                  placeholder="e.g. user-12345"
                  data-testid="ws-user-id-input"
                  aria-label="User ID"
                />
              </Field>
              <Button type="submit" variant="primary" disabled={!userIdInput.trim() || loading}>
                {loading ? "Loading…" : "Load Workspaces"}
              </Button>
            </form>
          </Card>

          {error && (
            <StatusBanner
              kind="err"
              title="Failed to load workspaces"
              description={error}
              className="ws__error"
              testId="ws-error"
            />
          )}

          {loading && workspaces.length === 0 && (
            <Loading label="Loading workspaces…" testId="ws-loading" />
          )}

          {/* Empty state — previously unreachable: this branch lived INSIDE
              the workspaces.length > 0 gate, so an empty list showed nothing. */}
          {!loading && workspaces.length === 0 && userId && (
            <div className="ws__empty" data-testid="ws-empty">
              <div className="ws__empty-icon" aria-hidden>
                <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="7" height="7" rx="1.5" />
                  <rect x="14" y="3" width="7" height="7" rx="1.5" />
                  <rect x="3" y="14" width="7" height="7" rx="1.5" />
                  <rect x="14" y="14" width="7" height="7" rx="1.5" />
                </svg>
              </div>
              <p className="ws__empty-title">No workspaces yet</p>
              <p className="ws__empty-sub">
                Create your first workspace to organize personal and business
                tax work separately.
              </p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setShowCreateForm(true)}
                data-testid="ws-empty-create"
              >
                + New Workspace
              </Button>
            </div>
          )}

              {/* Workspaces grid */}
              <div className="ws__workspaces-header">
                <h3 className="ws__section-title">My Workspaces</h3>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowCreateForm((v) => !v)}
                  data-testid="ws-toggle-create"
                >
                  {showCreateForm ? "Cancel" : "+ New Workspace"}
                </Button>
              </div>

              {showCreateForm && (
                <Card title="Create New Workspace" testId="ws-create-card" className="ws__create-card">
                  <form onSubmit={handleCreate} className="ws__create-form" data-testid="ws-create-form" noValidate>
                    <div className="ws__create-grid grid grid--2">
                      <Field label="Workspace Name *" error={formErrors.name}>
                        <input
                          type="text"
                          className="field__input"
                          value={createForm.name}
                          onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                          placeholder="My Business Workspace"
                          data-testid="ws-create-name-input"
                          aria-required="true"
                        />
                      </Field>
                      <Field label="Type">
                        <select
                          className="field__select"
                          value={createForm.type}
                          onChange={(e) => setCreateForm((f) => ({
                            ...f,
                            type: e.target.value as "personal" | "business",
                          }))}
                          data-testid="ws-create-type-select"
                        >
                          <option value="personal">Personal</option>
                          <option value="business">Business</option>
                        </select>
                      </Field>
                      <Field label="NTN (Optional)">
                        <input
                          type="text"
                          className="field__input"
                          value={createForm.ntn}
                          onChange={(e) => setCreateForm((f) => ({ ...f, ntn: e.target.value }))}
                          placeholder="1234567"
                          data-testid="ws-create-ntn-input"
                        />
                      </Field>
                    </div>
                    <div className="ws__create-actions">
                      <Button
                        type="submit"
                        variant="primary"
                        loading={creating}
                        disabled={creating}
                        data-testid="ws-create-submit"
                      >
                        {creating ? "Creating…" : "Create Workspace"}
                      </Button>
                    </div>
                  </form>
                </Card>
              )}

          {/* Loaded-state content: hero, stats, grid, tasks — only when the
              user has workspaces. */}
          {workspaces.length > 0 && !loading && (
            <>
              {/* Hero / active workspace section */}
              <section className="ws__hero card" data-testid="ws-hero">
                <div className="ws__hero-left">
                  <div className="ws__hero-avatar" aria-hidden>
                    <WorkspaceIcon type={activeWorkspace?.type ?? "personal"} />
                  </div>
                  <div className="ws__hero-info">
                    <p className="ws__hero-label">Active Workspace</p>
                    <h3 className="ws__hero-name">
                      {activeWorkspace?.name ?? "Personal Workspace"}
                    </h3>
                    {activeWorkspace?.ntn && (
                      <code className="ws__hero-ntn">NTN: {activeWorkspace.ntn}</code>
                    )}
                  </div>
                </div>
                <div className="ws__hero-badges">
                  <div className="ws__hero-badge">
                    <span className="ws__hero-badge-label">Compliance Score</span>
                    {loadingCalendar ? (
                      <Loading label="…" testId="ws-compliance-loading" />
                    ) : (
                      <ComplianceBadge score={calendarDashboard?.compliance_score ?? null} />
                    )}
                  </div>
                  <div className="ws__hero-badge">
                    <span className="ws__hero-badge-label">Health Score</span>
                    <Tag variant="accent">Coming Soon</Tag>
                  </div>
                </div>
              </section>

              {/* Quick stats */}
              <section className="ws__stats card" data-testid="ws-stats">
                <div className="ws__stat">
                  <span className="ws__stat-value">{workspaces.length}</span>
                  <span className="ws__stat-label">Total Workspaces</span>
                </div>
                <div className="ws__stat">
                  <span className="ws__stat-value">{totalMembers}</span>
                  <span className="ws__stat-label">Active Members</span>
                </div>
                <div className="ws__stat">
                  <span className="ws__stat-value">{pendingInvitations}</span>
                  <span className="ws__stat-label">Pending Invitations</span>
                </div>
                {calendarDashboard && (
                  <>
                    <div className="ws__stat">
                      <span className="ws__stat-value">{calendarDashboard.overdue_count}</span>
                      <span className="ws__stat-label">Overdue Items</span>
                    </div>
                    <div className="ws__stat">
                      <span className="ws__stat-value">{calendarDashboard.critical_upcoming_7d}</span>
                      <span className="ws__stat-label">Critical — 7 Days</span>
                    </div>
                  </>
                )}
              </section>


              <div className="ws__grid" data-testid="ws-grid">
                {workspaces.map((ws) => (
                  <WorkspaceCard
                    key={ws.id}
                    workspace={ws}
                    isActive={ws.id === activeWorkspaceId}
                    onSelect={handleSwitchWorkspace}
                  />
                ))}
              </div>

              {/* Quick links */}
              <h3 className="ws__section-title">Quick Links</h3>
              <div className="ws__quick-links" data-testid="ws-quick-links">
                <QuickLinkCard
                  label="Compliance Calendar"
                  to={`${basePath}/calendar`}
                  icon={
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  }
                />
                <QuickLinkCard
                  label="Tax Health"
                  to={`${basePath}/health`}
                  icon={
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                    </svg>
                  }
                />
                <QuickLinkCard
                  label="Notices"
                  to={`${basePath}/notices`}
                  icon={
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0-2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
                    </svg>
                  }
                />
                <QuickLinkCard
                  label="Invoices"
                  to={`${basePath}/invoices`}
                  icon={
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="6 9 6 2 18 2 18 9" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" />
                    </svg>
                  }
                />
                <QuickLinkCard
                  label="Documents"
                  to={`${basePath}/documents`}
                  icon={
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0-2-2V9z" /><polyline points="13 2 13 9 20 9" />
                    </svg>
                  }
                />
                <QuickLinkCard
                  label="Inbox"
                  to={`${basePath}/workspace?tab=inbox`}
                  icon={
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
                    </svg>
                  }
                />
              </div>

              {/* Compliance details */}
              {calendarDashboard && (
                <Card title="Compliance Status" testId="ws-compliance-card">
                  <Kv
                    rows={[
                      { key: "Taxpayer Type", value: calendarDashboard.taxpayer_type || "—" },
                      { key: "Compliance Grade", value: (
                          <Tag variant={calendarDashboard.compliance_grade === "A" ? "ok" :
                            calendarDashboard.compliance_grade === "B" ? "accent" :
                            calendarDashboard.compliance_grade === "C" ? "warn" : "err"
                          }>
                            {calendarDashboard.compliance_grade || "—"}
                          </Tag>
                        ) },
                      { key: "Total Events", value: calendarDashboard.total_events },
                      { key: "Overdue", value: <Tag variant={calendarDashboard.overdue_count > 0 ? "err" : "ok"}>
                          {calendarDashboard.overdue_count}
                        </Tag> },
                      { key: "Critical (30 days)", value: calendarDashboard.critical_upcoming_30d },
                      { key: "Critical (7 days)", value: calendarDashboard.critical_upcoming_7d },
                      { key: "Summary", value: calendarDashboard.summary_message || "—" },
                    ]}
                    testId="ws-compliance-kv"
                  />
                </Card>
              )}

              {/* Recent activity */}
              {upcomingTasks.length > 0 && (
                <Card title="Upcoming Tasks" subtitle="Next 14 days" testId="ws-upcoming-card">
                  <div className="ws__tasks-list" data-testid="ws-tasks-list">
                    {upcomingTasks.slice(0, 10).map((task, idx) => (
                      <div key={idx} className={clsx("ws__task", task.is_overdue && "ws__task--overdue")} data-testid={`ws-task-${idx}`}>
                        <div className="ws__task-priority">
                          <Tag
                            variant={
                              task.priority === "critical" ? "err" :
                              task.priority === "high" ? "warn" :
                              task.priority === "medium" ? "accent" : "default"
                            }
                          >
                            {task.priority}
                          </Tag>
                        </div>
                        <div className="ws__task-body">
                          <span className="ws__task-title">{task.title}</span>
                          <span className="ws__task-category">{task.category} — {task.event_type}</span>
                        </div>
                        <div className="ws__task-due">
                          <span className={clsx("ws__task-days", task.is_overdue && "ws__task-days--overdue")}>
                            {task.is_overdue
                              ? `${Math.abs(task.days_remaining)} days overdue`
                              : task.days_remaining === 0
                              ? "Due today"
                              : `${task.days_remaining} days left`}
                          </span>
                          <span className="ws__task-date">
                            {new Date(task.due_date).toLocaleDateString("en-PK", {
                              day: "numeric", month: "short",
                            })}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </section>
    </ErrorBoundary>
  );
}
