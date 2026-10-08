import { useLocation, useNavigate } from "react-router-dom";
import { findSectionByPath as findPersonalSection } from "@/state/personalNav";
import { findBusinessSectionByPath as findBusinessSection } from "@/state/businessNav";
import { WORKSPACES, useWorkspace } from "@/state/workspace";
import { useAuth } from "@/state/auth";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

interface HeaderProps {
  onToggleSidebar: () => void;
}

export function Header({ onToggleSidebar }: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const activeWs = useWorkspace((s) => s.active);
  const signOut = useAuth((s) => s.signOut);
  const user = useAuth((s) => s.user);
  const email = user?.email ?? "";

  const handleSignOut = async () => {
    await signOut();
    navigate("/", { replace: true });
  };
  const isBusiness = location.pathname.startsWith("/business");
  const current = isBusiness
    ? findBusinessSection(location.pathname)
    : findPersonalSection(location.pathname);

  return (
    <header className="app-header" role="banner">
      <button
        type="button"
        className="app-header__menu"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
        data-testid="sidebar-toggle"
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden>
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <div className="app-header__title-block">
        <div className="app-header__title-row">
          <span className="app-header__workspace-pill">{WORKSPACES[activeWs].label}</span>
          <h1 className="app-header__title">{current?.label ?? "FBR Tax & Compliance"}</h1>
        </div>
        {current ? <p className="app-header__subtitle">{current.blurb}</p> : null}
      </div>

      <div className="app-header__right">
        <WorkspaceSwitcher />
        <button
          type="button"
          className="btn btn--ghost btn--sm app-header__notif"
          onClick={() => navigate(isBusiness ? "/business/workspace?tab=inbox" : "/personal/workspace?tab=inbox")}
          title="Notifications"
          aria-label="Notifications"
          data-testid="header-notifications"
        >
          <svg
            viewBox="0 0 24 24"
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.7 21a2 2 0 0 1-3.4 0" />
          </svg>
          <span className="app-header__btn-label">Notifications</span>
        </button>
        <button
          type="button"
          className="btn btn--ghost btn--sm app-header__user"
          onClick={handleSignOut}
          title={email}
          data-testid="sign-out"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
