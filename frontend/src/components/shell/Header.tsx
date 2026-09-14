import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { findSectionByPath as findPersonalSection } from "@/state/personalNav";
import { findBusinessSectionByPath as findBusinessSection } from "@/state/businessNav";
import { WORKSPACES, useWorkspace } from "@/state/workspace";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

interface HeaderProps {
  onToggleSidebar: () => void;
  apiHealthy: boolean | null;
}

export function Header({ onToggleSidebar, apiHealthy }: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const activeWs = useWorkspace((s) => s.active);
  const isBusiness = location.pathname.startsWith("/business");
  const current = isBusiness
    ? findBusinessSection(location.pathname)
    : findPersonalSection(location.pathname);

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const dateLabel = now.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

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
        <nav className="app-header__crumbs" aria-label="Breadcrumb">
          <span>FBR</span>
          <span aria-hidden>/</span>
          <span>{WORKSPACES[activeWs].label}</span>
          {current ? (
            <>
              <span aria-hidden>/</span>
              <span aria-current="page">{current.label}</span>
            </>
          ) : null}
        </nav>
        <div className="app-header__title-row">
          <span className="app-header__workspace-pill">{WORKSPACES[activeWs].label}</span>
          <h1 className="app-header__title">{current?.label ?? "FBR Tax & Compliance"}</h1>
        </div>
        {current ? <p className="app-header__subtitle">{current.blurb}</p> : null}
      </div>

      <div className="app-header__right">
        <WorkspaceSwitcher />
        <div className="app-header__meta">
          <span
            className={`api-status api-status--${apiHealthy === null ? "unknown" : apiHealthy ? "ok" : "err"}`}
            title={apiHealthy === null ? "API status not yet checked" : apiHealthy ? "Backend reachable" : "Backend unreachable"}
            data-testid="api-status"
          >
            <span className="api-status__dot" />
            <span className="api-status__label">
              {apiHealthy === null ? "API ?" : apiHealthy ? "API Connected" : "API Offline"}
            </span>
          </span>
          <span className="app-header__date">{dateLabel}</span>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => navigate(isBusiness ? "/business/inbox" : "/personal/inbox")}
          >
            Notifications
          </button>
        </div>
      </div>
    </header>
  );
}
