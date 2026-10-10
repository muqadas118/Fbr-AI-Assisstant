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
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";
import { useAuth } from "@/state/auth";
import type {
  TeamDashboard,
} from "@/lib/api";

interface AddSubordinateForm {
  name: string;
  email: string;
  password: string;
  role: string;
  ntn: string;
  cnic: string;
  organization: string;
  phone: string;
}

interface InviteForm {
  email: string;
  role: string;
}

const EMPTY_FORM: AddSubordinateForm = {
  name: "",
  email: "",
  password: "",
  role: "subordinate",
  ntn: "",
  cnic: "",
  organization: "",
  phone: "",
};

const EMPTY_INVITE: InviteForm = {
  email: "",
  role: "accountant",
};

/** Shape of one role entry from GET /team/roles. */
interface RoleDetails {
  label?: string;
  permissions?: string[];
}

function memberRoleVariant(role: string): "accent" | "warn" | "default" {
  const r = role?.toLowerCase() ?? "";
  if (r === "owner" || r === "admin") return "accent";
  if (r === "manager") return "warn";
  return "default";
}

export function SubordinatesPage() {
  // session-derived id with manual override
  const sessionId = useAuth((s) => s.user?.id ?? "");
  const { show: notify } = useNotification();
  const [teamId, setTeamId] = useState("");
  const [teamIdInput, setTeamIdInput] = useState("");
  useEffect(() => {
    if (sessionId && !teamId) {
      setTeamId(sessionId);
      setTeamIdInput(sessionId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
  const [teamDashboard, setTeamDashboard] = useState<TeamDashboard | null>(null);
  const [roles, setRoles] = useState<Record<string, RoleDetails> | null>(null);
  const [loadingRoles, setLoadingRoles] = useState(false);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [addForm, setAddForm] = useState<AddSubordinateForm>(EMPTY_FORM);
  const [inviteForm, setInviteForm] = useState<InviteForm>(EMPTY_INVITE);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof AddSubordinateForm, string>>>({});
  const [inviteErrors, setInviteErrors] = useState<Partial<Record<keyof InviteForm, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [activeMemberId, setActiveMemberId] = useState<string | null>(null);

  // Fetch roles on mount
  useEffect(() => {
    void (async () => {
      setLoadingRoles(true);
      try {
        const r = await api.team.getRoles();
        // API wraps the map in an envelope: { roles: { admin: {...}, ... } }
        const payload = (r as { roles?: Record<string, RoleDetails> }).roles ?? (r as Record<string, RoleDetails>);
        setRoles(payload);
      } catch {
        // roles are non-critical
      } finally {
        setLoadingRoles(false);
      }
    })();
  }, []);

  const fetchTeamDashboard = useCallback(async (tid: string) => {
    if (!tid.trim()) return;
    setLoadingDashboard(true);
    setError(null);
    try {
      const data = await api.team.getTeamDashboard(tid.trim());
      setTeamDashboard(data);
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Network error — could not reach the server.");
      } else if (err instanceof ApiError) {
        setError(`API error (${err.status}): ${err.detail}`);
      } else {
        setError("An unexpected error occurred.");
      }
      setTeamDashboard(null);
    } finally {
      setLoadingDashboard(false);
    }
  }, []);

  const handleLoadTeam = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    setTeamId(teamIdInput.trim());
    void fetchTeamDashboard(teamIdInput.trim());
  }, [teamIdInput, fetchTeamDashboard]);

  const validateAddForm = useCallback((): boolean => {
    const errs: Partial<Record<keyof AddSubordinateForm, string>> = {};
    if (!addForm.name.trim()) errs.name = "Name is required.";
    if (!addForm.email.trim()) errs.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addForm.email)) errs.email = "Invalid email format.";
    if (!addForm.password) errs.password = "Password is required.";
    else if (addForm.password.length < 6) errs.password = "Password must be at least 6 characters.";
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  }, [addForm]);

  const handleAddSubordinate = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateAddForm()) return;
    setSubmitting(true);
    try {
      await api.team.register({
        name: addForm.name.trim(),
        email: addForm.email.trim(),
        password: addForm.password,
        role: addForm.role || "subordinate",
        ntn: addForm.ntn.trim() || undefined,
        cnic: addForm.cnic.trim() || undefined,
        organization: addForm.organization.trim() || undefined,
        phone: addForm.phone.trim() || undefined,
      });
      notify("ok", "Subordinate registered successfully.");
      setAddForm(EMPTY_FORM);
      setFormErrors({});
      if (teamId) void fetchTeamDashboard(teamId);
    } catch (err) {
      if (err instanceof ApiError) {
        notify("err", `Registration failed: ${err.detail}`);
      } else if (err instanceof NetworkError) {
        notify("err", "Network error — registration failed.");
      } else {
        notify("err", "An unexpected error occurred during registration.");
      }
    } finally {
      setSubmitting(false);
    }
  }, [addForm, validateAddForm, teamId, fetchTeamDashboard, notify]);

  const validateInviteForm = useCallback((): boolean => {
    const errs: Partial<Record<keyof InviteForm, string>> = {};
    if (!inviteForm.email.trim()) errs.email = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(inviteForm.email)) errs.email = "Invalid email format.";
    setInviteErrors(errs);
    return Object.keys(errs).length === 0;
  }, [inviteForm]);

  const handleInvite = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateInviteForm()) return;
    if (!teamId.trim()) {
      notify("warn", "Load a team first — an invitation needs a team ID.");
      return;
    }
    setInviting(true);
    try {
      // Real invitation: POST /team/invite. No throwaway account is created —
      // the invitee accepts through the invitation email/flow instead.
      const invitation = await api.team.invite({
        team_id: teamId.trim(),
        email: inviteForm.email.trim(),
        role: inviteForm.role || "accountant",
      });
      notify("ok", `Invitation sent to ${invitation.email} (status: ${invitation.status}).`);
      setInviteForm(EMPTY_INVITE);
      setInviteErrors({});
      void fetchTeamDashboard(teamId.trim());
    } catch (err) {
      if (err instanceof ApiError) {
        notify("err", `Invitation failed: ${err.detail}`);
      } else if (err instanceof NetworkError) {
        notify("err", "Network error — invitation failed.");
      } else {
        notify("err", "An unexpected error occurred.");
      }
    } finally {
      setInviting(false);
    }
  }, [inviteForm, validateInviteForm, teamId, fetchTeamDashboard, notify]);

  const memberJoinedDate = (joinedAt: string) => {
    try {
      return new Date(joinedAt).toLocaleDateString("en-PK", {
        day: "numeric", month: "short", year: "numeric",
      });
    } catch {
      return joinedAt;
    }
  };

  return (
    <ErrorBoundary>
      <section className="page page--subordinates">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Team</div>
            <h2 className="page__title">Subordinates</h2>
            <p className="page__subtitle">
              Manage your team members, delegate access, and verify subordinate credentials.
            </p>
          </div>
        </header>

        <div className="page__content">
          {/* Team ID setup */}
          <Card className="sub__setup" testId="sub-setup">
            <form onSubmit={handleLoadTeam} className="sub__setup-form" data-testid="sub-setup-form">
              <Field
                label="Team ID"
                helperText="Enter your team ID to load the team dashboard and member list."
              >
                <input
                  type="text"
                  className="field__input"
                  value={teamIdInput}
                  onChange={(e) => setTeamIdInput(e.target.value)}
                  placeholder="e.g. team-abc123"
                  data-testid="sub-team-id-input"
                  aria-label="Team ID"
                />
              </Field>
              <Button type="submit" variant="primary" disabled={!teamIdInput.trim() || loadingDashboard}>
                {loadingDashboard ? "Loading…" : "Load Team"}
              </Button>
            </form>
          </Card>

          {error && (
            <StatusBanner
              kind="err"
              title="Failed to load team"
              description={error}
              className="sub__error"
              testId="sub-error"
            />
          )}

          {/* Two-column form area */}
          <div className="sub__forms">
            {/* Add Subordinate Form */}
            <Card
              title="Add Subordinate"
              subtitle="Register a new team member"
              testId="sub-add-card"
              className="sub__add-card"
            >
              <form onSubmit={handleAddSubordinate} className="sub__form" data-testid="sub-add-form" noValidate>
                <div className="sub__form-grid grid grid--2">
                  <Field label="Full Name *" error={formErrors.name}>
                    <input
                      type="text"
                      className="field__input"
                      value={addForm.name}
                      onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))}
                      placeholder="Ahmed Khan"
                      autoComplete="name"
                      data-testid="sub-name-input"
                      aria-required="true"
                    />
                  </Field>

                  <Field label="Email *" error={formErrors.email}>
                    <input
                      type="email"
                      className="field__input"
                      value={addForm.email}
                      onChange={(e) => setAddForm((f) => ({ ...f, email: e.target.value }))}
                      placeholder="ahmed@example.com"
                      autoComplete="email"
                      data-testid="sub-email-input"
                      aria-required="true"
                    />
                  </Field>

                  <Field label="Password *" error={formErrors.password}>
                    <input
                      type="password"
                      className="field__input"
                      value={addForm.password}
                      onChange={(e) => setAddForm((f) => ({ ...f, password: e.target.value }))}
                      placeholder="Min 6 characters"
                      autoComplete="new-password"
                      data-testid="sub-password-input"
                      aria-required="true"
                    />
                  </Field>

                  <Field label="Role">
                    <select
                      className="field__select"
                      value={addForm.role}
                      onChange={(e) => setAddForm((f) => ({ ...f, role: e.target.value }))}
                      data-testid="sub-role-select"
                    >
                      <option value="subordinate">Subordinate</option>
                      <option value="manager">Manager</option>
                      <option value="admin">Admin</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </Field>

                  <Field label="NTN (Optional)">
                    <input
                      type="text"
                      className="field__input"
                      value={addForm.ntn}
                      onChange={(e) => setAddForm((f) => ({ ...f, ntn: e.target.value }))}
                      placeholder="1234567"
                      data-testid="sub-ntn-input"
                    />
                  </Field>

                  <Field label="CNIC (Optional)">
                    <input
                      type="text"
                      className="field__input"
                      value={addForm.cnic}
                      onChange={(e) => setAddForm((f) => ({ ...f, cnic: e.target.value }))}
                      placeholder="12345-1234567-1"
                      data-testid="sub-cnic-input"
                    />
                  </Field>

                  <Field label="Organization (Optional)">
                    <input
                      type="text"
                      className="field__input"
                      value={addForm.organization}
                      onChange={(e) => setAddForm((f) => ({ ...f, organization: e.target.value }))}
                      placeholder="Company Name"
                      data-testid="sub-org-input"
                    />
                  </Field>

                  <Field label="Phone (Optional)">
                    <input
                      type="tel"
                      className="field__input"
                      value={addForm.phone}
                      onChange={(e) => setAddForm((f) => ({ ...f, phone: e.target.value }))}
                      placeholder="+92 300 1234567"
                      data-testid="sub-phone-input"
                    />
                  </Field>
                </div>

                <div className="sub__form-actions">
                  <Button
                    type="submit"
                    variant="primary"
                    loading={submitting}
                    disabled={submitting}
                    data-testid="sub-add-submit"
                  >
                    {submitting ? "Registering…" : "Register Subordinate"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => { setAddForm(EMPTY_FORM); setFormErrors({}); }}
                    data-testid="sub-add-reset"
                  >
                    Clear
                  </Button>
                </div>
              </form>
            </Card>

            {/* Invite User Form */}
            <Card
              title="Invite User"
              subtitle="Send an invitation to join the team"
              testId="sub-invite-card"
              className="sub__invite-card"
            >
              <form onSubmit={handleInvite} className="sub__form" data-testid="sub-invite-form" noValidate>
                <Field label="Email *" error={inviteErrors.email}>
                  <input
                    type="email"
                    className="field__input"
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))}
                    placeholder="colleague@example.com"
                    data-testid="sub-invite-email-input"
                    aria-required="true"
                  />
                </Field>

                <Field label="Role">
                  <select
                    className="field__select"
                    value={inviteForm.role}
                    onChange={(e) => setInviteForm((f) => ({ ...f, role: e.target.value }))}
                    data-testid="sub-invite-role-select"
                  >
                    {/* Values must match the backend UserRole enum
                        (admin|manager|accountant|viewer|guest) — POST /team/invite
                        rejects anything else with 400. */}
                    <option value="accountant">Accountant</option>
                    <option value="manager">Manager</option>
                    <option value="admin">Admin</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </Field>

                <div className="sub__form-actions">
                  <Button
                    type="submit"
                    variant="secondary"
                    loading={inviting}
                    disabled={inviting}
                    data-testid="sub-invite-submit"
                  >
                    {inviting ? "Inviting…" : "Send Invitation"}
                  </Button>
                </div>
              </form>

              {/* Roles reference */}
              {loadingRoles ? (
                <Loading label="Loading roles…" testId="sub-roles-loading" />
              ) : roles ? (
                <div className="sub__roles-ref">
                  <h4 className="sub__roles-title">Role Capabilities</h4>
                  <div className="sub__roles-list">
                    {Object.entries(roles).map(([role, details]) => (
                      <div key={role} className="sub__role-item">
                        <Tag variant={memberRoleVariant(role)}>{details?.label ?? role}</Tag>
                        <span className="sub__role-desc">
                          {details?.permissions?.length
                            ? details.permissions.join(" · ")
                            : "No permissions — read-only access."}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </Card>
          </div>

          {/* Team Dashboard */}
          {loadingDashboard && !teamDashboard && (
            <Loading label="Loading team dashboard…" testId="sub-dashboard-loading" />
          )}

          {teamDashboard && (
            <>
              {/* Team info */}
              <Card title="Team Overview" testId="sub-team-info">
                <Kv
                  rows={[
                    { key: "Team Name", value: teamDashboard.team.name || "—" },
                    { key: "Owner ID", value: teamDashboard.team.owner_id || "—" },
                    { key: "NTN", value: teamDashboard.team.ntn ? (
                        <code className="sub__mono">{teamDashboard.team.ntn}</code>
                      ) : "—" },
                    { key: "Plan", value: <Tag variant="accent">{teamDashboard.team.plan || "—"}</Tag> },
                    { key: "Organization Type", value: teamDashboard.team.organization_type || "—" },
                    { key: "Status", value: <Tag variant={teamDashboard.team.is_active ? "ok" : "err"}>
                        {teamDashboard.team.is_active ? "Active" : "Inactive"}
                      </Tag> },
                    { key: "Member Count", value: teamDashboard.member_count ?? 0 },
                    { key: "Pending Invitations", value: teamDashboard.pending_invitations ?? 0 },
                    { key: "Created", value: memberJoinedDate(teamDashboard.team.created_at) },
                  ]}
                  testId="sub-team-kv"
                />
              </Card>

              {/* Members list */}
              <Card title="Team Members" testId="sub-members-card">
                {teamDashboard.members.length === 0 ? (
                  <StatusBanner
                    kind="info"
                    title="No members"
                    description="This team has no members yet. Add a subordinate or send an invitation above."
                    testId="sub-members-empty"
                  />
                ) : (
                  <div className="sub__members-list" data-testid="sub-members-list">
                    {teamDashboard.members.map((member) => (
                      <div
                        key={member.id}
                        className={clsx(
                          "sub__member",
                          activeMemberId === member.id && "sub__member--active",
                        )}
                        data-testid={`sub-member-${member.id}`}
                      >
                        <div className="sub__member-header">
                          <div className="sub__member-avatar" aria-hidden>
                            {member.role?.charAt(0).toUpperCase() ?? "?"}
                          </div>
                          <div className="sub__member-info">
                            <div className="sub__member-top">
                              <span className="sub__member-role">{member.role}</span>
                              <Tag variant={member.is_active ? "ok" : "err"}>
                                {member.is_active ? "Active" : "Inactive"}
                              </Tag>
                            </div>
                            <span className="sub__member-id">ID: {member.user_id || member.id}</span>
                            <span className="sub__member-joined">Joined: {memberJoinedDate(member.joined_at)}</span>
                          </div>
                          <div className="sub__member-actions">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setActiveMemberId(
                                activeMemberId === member.id ? null : member.id,
                              )}
                              data-testid={`sub-member-expand-${member.id}`}
                            >
                              {activeMemberId === member.id ? "Collapse" : "Details"}
                            </Button>
                          </div>
                        </div>

                        {activeMemberId === member.id && (
                          <div className="sub__member-details" data-testid={`sub-member-details-${member.id}`}>
                            <div className="sub__member-details-row">
                              <span className="sub__detail-label">Member ID</span>
                              <code className="sub__mono">{member.user_id || member.id}</code>
                            </div>
                            <div className="sub__member-details-row">
                              <span className="sub__detail-label">Team ID</span>
                              <code className="sub__mono">{member.team_id}</code>
                            </div>
                            <div className="sub__member-details-row">
                              <span className="sub__detail-label">Role</span>
                              <Tag variant={memberRoleVariant(member.role)}>{member.role}</Tag>
                            </div>
                            {/* Credential verification is intentionally absent:
                                the backend TeamMember row (GET /team/dashboard/{id})
                                carries only team_id / user_id / role / joined_at /
                                is_active — no NTN — and no authed endpoint exposes
                                another member's NTN (GET /team/user-dashboard/{id}
                                is restricted to the caller). Without an NTN there is
                                nothing to send to /verify/ntn, so the old block
                                could never render a result. */}
                            <p className="sub__verif-hint">
                              Credential verification needs the member's NTN, which the
                              team API does not return — verify NTNs from the
                              Verification Centre instead.
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {/* Pending invitations */}
              {teamDashboard.invitations && teamDashboard.invitations.length > 0 && (
                <Card title="Pending Invitations" testId="sub-invitations-card">
                  <div className="sub__invitations-list" data-testid="sub-invitations-list">
                    {teamDashboard.invitations.map((inv) => (
                      <div key={inv.id} className="sub__invitation" data-testid={`sub-invitation-${inv.id}`}>
                        <div className="sub__inv-info">
                          <span className="sub__inv-email">{inv.email}</span>
                          <div className="sub__inv-meta">
                            <Tag variant="warn">{inv.role}</Tag>
                            <Tag
                              variant={inv.status === "pending" ? "warn" : inv.status === "accepted" ? "ok" : "default"}
                            >
                              {inv.status}
                            </Tag>
                            <span className="sub__inv-date">
                              Invited: {memberJoinedDate(inv.invited_at)}
                            </span>
                            <span className="sub__inv-date">
                              Expires: {memberJoinedDate(inv.expires_at)}
                            </span>
                          </div>
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
