import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useState, type ReactNode } from "react";
import { useAuth } from "@/state/auth";
import { authApi } from "@/lib/api";
import { useWorkspace, type WorkspaceId } from "@/state/workspace";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";

interface RequireAuthProps {
  children?: ReactNode;
}

function workspaceLabel(ws: WorkspaceId): string {
  return ws === "business" ? "Business" : "Personal";
}

export function RequireAuth({ children }: RequireAuthProps) {
  // NOTE: every hook must run unconditionally BEFORE any early return —
  // React crashes with "Rendered fewer hooks than expected" otherwise,
  // which used to break the login flow mid-transition (token null -> set).
  const token = useAuth((s) => s.token);
  const loading = useAuth((s) => s.loading);
  const initialized = useAuth((s) => s.initialized);
  const preferred = useAuth((s) => s.user?.preferred_workspace);
  const updateUser = useAuth((s) => s.updateUser);
  const setAllowedWorkspace = useWorkspace((s) => s.setAllowed);
  const location = useLocation();
  const navigate = useNavigate();
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

  // Which workspace the URL asks for (null outside the two workspaces,
  // e.g. /onboarding — no gating there).
  const requested: WorkspaceId | null = location.pathname.startsWith("/business")
    ? "business"
    : location.pathname.startsWith("/personal")
      ? "personal"
      : null;
  const allocation: WorkspaceId | null =
    preferred === "business" || preferred === "personal" ? preferred : null;

  if (!initialized || loading) {
    return (
      <div
        className="state state--loading"
        role="status"
        aria-live="polite"
        data-testid="auth-loading"
        style={{ minHeight: "40vh", display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <Spinner size="lg" />
        <span style={{ marginLeft: 12 }}>Checking session…</span>
      </div>
    );
  }

  if (!token) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}${location.hash}` }}
      />
    );
  }

  // Gating: allocated workspace ke ilawa doosri workspace "nazr na ayee".
  // Instead of a hard one-way redirect, the user gets an escape hatch:
  // continue in the allocated workspace, or switch the account's
  // allocation (POST /auth/workspace) and stay on the requested page.
  if (allocation && requested && allocation !== requested) {
    const switchWorkspace = async () => {
      if (switching) return;
      setSwitching(true);
      setSwitchError(null);
      try {
        // Persist the new primary workspace on the backend user row
        // (idempotent — the latest choice wins).
        await authApi.allocateWorkspace(requested, token);
        updateUser({ preferred_workspace: requested });
        setAllowedWorkspace(requested);
        // Re-render shows the requested workspace; no navigation needed.
      } catch (err) {
        setSwitchError(
          err instanceof Error ? err.message : "Workspace switch failed. Please try again.",
        );
        setSwitching(false);
      }
    };

    return (
      <div
        className="state state--full"
        role="status"
        aria-live="polite"
        data-testid="workspace-gate"
      >
        <div className="state__body" style={{ textAlign: "center" }}>
          <h1 className="state__title">Workspace locked to your allocation</h1>
          <p>
            Your account is allocated to the {workspaceLabel(allocation)} workspace.
            Continue there, or switch this account to the {workspaceLabel(requested)} workspace.
          </p>
          <div
            style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 12 }}
          >
            <Button
              variant="secondary"
              onClick={() => navigate(`/${allocation}/overview`, { replace: true })}
              data-testid="workspace-gate-continue"
            >
              Go to {workspaceLabel(allocation)}
            </Button>
            <Button
              variant="primary"
              loading={switching}
              onClick={() => void switchWorkspace()}
              data-testid="workspace-gate-switch"
            >
              Switch to {workspaceLabel(requested)}
            </Button>
          </div>
          {switchError ? (
            <p className="field__error" role="alert" data-testid="workspace-gate-error">
              {switchError}
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  if (children) return <>{children}</>;
  return <Outlet />;
}
