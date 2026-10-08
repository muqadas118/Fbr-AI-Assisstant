import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "@/state/auth";
import { Spinner } from "@/components/ui/Spinner";

interface RequireAuthProps {
  children?: ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  // NOTE: every hook must run unconditionally BEFORE any early return —
  // React crashes with "Rendered fewer hooks than expected" otherwise,
  // which used to break the login flow mid-transition (token null -> set).
  const token = useAuth((s) => s.token);
  const loading = useAuth((s) => s.loading);
  const initialized = useAuth((s) => s.initialized);
  const preferred = useAuth((s) => s.user?.preferred_workspace);
  const location = useLocation();

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

  // Gating: allocated workspace ke ilawa doosri workspace "nazr na ayee" —
  // direct URL access bhi apni primary workspace par redirect ho jata hai.
  if (preferred === "business" && location.pathname.startsWith("/personal")) {
    return <Navigate to="/business/overview" replace />;
  }
  if (preferred === "personal" && location.pathname.startsWith("/business")) {
    return <Navigate to="/personal/overview" replace />;
  }

  if (children) return <>{children}</>;
  return <Outlet />;
}
