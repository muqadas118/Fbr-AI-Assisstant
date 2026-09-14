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
  TeamMember,
  VerificationResponse,
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

interface MemberVerification {
  ntn: string;
  ntnStatus?: VerificationResponse;
  filerStatus?: VerificationResponse;
  loading: boolean;
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
  role: "subordinate",
};

function memberRoleVariant(role: string): "accent" | "warn" | "default" {
  const r = role?.toLowerCase() ?? "";
  if (r === "owner" || r === "admin") return "accent";
  if (r === "manager") return "warn";
  return "default";
}

function VerificationBadge({ label, result }: { label: string; result?: VerificationResponse }) {
  if (!result) return null;
  return (
    <div className="sub__verif-row">
      <span className="sub__verif-label">{label}</span>
      <Tag variant={result.is_verified ? "ok" : "err"}>
        {result.is_verified ? "Verified" : "Not Verified"}
      </Tag>
    </div>
  );
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
  const [roles, setRoles] = useState<Record<string, unknown> | null>(null);
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
  const [memberVerifications, setMemberVerifications] = useState<Record<string, MemberVerification>>({});

  // Fetch roles on mount
  useEffect(() => {
    void (async () => {
      setLoadingRoles(true);
      try {
        const r = await api.team.getRoles();
        setRoles(r);
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
    setInviting(true);
    try {
      // Team invitation endpoint — uses register with invitation flow
      const tempPassword = `${crypto.randomUUID().slice(0, 12)}Tmp!1`;
      await api.team.register({
        email: inviteForm.email.trim(),
        password: tempPassword,
        name: inviteForm.email.split("@")[0],
        role: inviteForm.role || "subordinate",
      });
      notify("ok", `Invitation sent to ${inviteForm.email}`);
      setInviteForm(EMPTY_INVITE);
      setInviteErrors({});
      if (teamId) void fetchTeamDashboard(teamId);
    } catch (err) {
      if (err instanceof ApiError) {
        notify("err", `Invitation failed: ${err.detail}`);
      } else {
        notify("err", "An unexpected error occurred.");
      }
    } finally {
      setInviting(false);
    }
  }, [inviteForm, validateInviteForm, teamId, fetchTeamDashboard, notify]);

  const handleVerifyMember = useCallback(async (member: TeamMember, memberNtn?: string) => {
    if (!memberNtn) {
      notify("warn", "No NTN on record for this member.");
      return;
    }
    setMemberVerifications((prev) => ({
      ...prev,
      [member.id]: {
        ...prev[member.id],
        ntn: memberNtn,
        loading: true,
      },
    }));
    try {
      const [ntnResult, filerResult] = await Promise.allSettled([
        api.verify.ntn(memberNtn),
        api.verify.filer(memberNtn),
      ]);
      setMemberVerifications((prev) => ({
        ...prev,
        [member.id]: {
          ntn: memberNtn,
          ntnStatus: ntnResult.status === "fulfilled" ? ntnResult.value : undefined,
          filerStatus: filerResult.status === "fulfilled" ? filerResult.value : undefined,
          loading: false,
        },
      }));
    } catch {
      notify("err", "Verification check failed.");
      setMemberVerifications((prev) => ({
        ...prev,
        [member.id]: { ...prev[member.id], loading: false, ntn: memberNtn },
      }));
    }
  }, [notify]);

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
                <div className="sub__form-grid">
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
                    <option value="subordinate">Subordinate</option>
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
                        <Tag variant={memberRoleVariant(role)}>{role}</Tag>
                        <span className="sub__role-desc">
                          {typeof details === "object" && details !== null
                            ? Object.entries(details as Record<string, unknown>)
                                .map(([k, v]) => `${k}: ${String(v)}`)
                                .join(" | ")
                            : String(details ?? "")}
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
                            <div className="sub__verif-section">
                              <h5 className="sub__verif-title">Credential Verification</h5>
                              {memberVerifications[member.id]?.loading ? (
                                <Loading label="Verifying…" testId={`sub-verif-loading-${member.id}`} />
                              ) : (
                                <>
                                  <VerificationBadge
                                    label="NTN Status"
                                    result={memberVerifications[member.id]?.ntnStatus}
                                  />
                                  <VerificationBadge
                                    label="Filer Status"
                                    result={memberVerifications[member.id]?.filerStatus}
                                  />
                                  {memberVerifications[member.id]?.ntn && (
                                    <div className="sub__verif-check">
                                      <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => handleVerifyMember(
                                          member,
                                          memberVerifications[member.id]?.ntn,
                                        )}
                                        data-testid={`sub-verify-${member.id}`}
                                      >
                                        Re-verify Credentials
                                      </Button>
                                    </div>
                                  )}
                                  {!memberVerifications[member.id] && (
                                    <p className="sub__verif-hint">
                                      No NTN on record for this member. Add an NTN to enable verification.
                                    </p>
                                  )}
                                </>
                              )}
                            </div>
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
