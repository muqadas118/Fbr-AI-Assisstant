import { NavLink } from "react-router-dom";
import clsx from "clsx";
import type { ReactNode } from "react";

export interface NavSection {
  id: string;
  label: string;
  blurb: string;
  path: string;
  icon: ReactNode;
  status: "ready" | "partial" | "stub";
}

export interface SidebarConfig {
  sections: NavSection[];
  sectionLabel: string;
  footerText: string;
  navLabel: string;
  testId: string;
}

interface SidebarProps extends SidebarConfig {
  collapsed: boolean;
  onClose?: () => void;
}

function statusLabel(status: NavSection["status"]): string | null {
  if (status === "ready") return null;
  if (status === "partial") return "Preview";
  return "Stub";
}

export function Sidebar({ collapsed, onClose, sections, sectionLabel, footerText, navLabel, testId }: SidebarProps) {
  return (
    <aside className={clsx("sidebar", collapsed && "sidebar--collapsed")} aria-label={navLabel}>
      <div className="sidebar__brand" aria-hidden={collapsed}>
        <span className="sidebar__brand-mark">FBR</span>
        <span className="sidebar__brand-name">Tax &amp; Compliance</span>
      </div>

      <div className="sidebar__section-label" aria-hidden={collapsed}>
        {sectionLabel}
      </div>

      <nav className="sidebar__nav" data-testid={testId}>
        {sections.map((section) => {
          const label = statusLabel(section.status);
          return (
            <NavLink
              key={section.id}
              to={section.path}
              className={({ isActive }) =>
                clsx("sidebar__item", isActive && "sidebar__item--active")
              }
              onClick={onClose}
              title={section.blurb}
              data-section={section.id}
            >
              <span className="sidebar__icon-wrap">{section.icon}</span>
              <span className="sidebar__label">{section.label}</span>
              {label ? <span className={`sidebar__status sidebar__status--${section.status}`}>{label}</span> : null}
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar__footer" aria-hidden={collapsed}>
        <span className="sidebar__footer-dot" />
        <span className="sidebar__footer-text">{footerText}</span>
      </div>
    </aside>
  );
}
