import { useLocation, useNavigate } from "react-router-dom";
import { findSectionByPath as findPersonalSection } from "@/state/personalNav";
import { findBusinessSectionByPath as findBusinessSection } from "@/state/businessNav";
import { WORKSPACES, useWorkspace } from "@/state/workspace";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

interface HeaderProps {
  onToggleSidebar: () => void;
}

export function Header({ onToggleSidebar }: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const activeWs = useWorkspace((s) => s.active);
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
          className="btn btn--ghost btn--sm"
          onClick={() => navigate(isBusiness ? "/business/workspace?tab=inbox" : "/personal/workspace?tab=inbox")}
        >
          Notifications
        </button>
      </div>
    </header>
  );
}
