import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import clsx from "clsx";
import type { ReactNode } from "react";

export interface NavSection {
  id: string;
  label: string;
  blurb: string;
  path: string;
  icon: ReactNode;
  status: "ready" | "partial" | "stub";
  group?: string;
  bottomUtility?: boolean;
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

const ChevronIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
  >
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export function Sidebar({ collapsed, onClose, sections, sectionLabel, footerText, navLabel, testId }: SidebarProps) {
  const location = useLocation();
  const mainSections = sections.filter((s) => !s.bottomUtility);
  const utilities = sections.filter((s) => s.bottomUtility);

  // Group order is derived once from the flat section list.
  const groupOrder: string[] = [];
  for (const section of mainSections) {
    if (section.group && !groupOrder.includes(section.group)) groupOrder.push(section.group);
  }
  const grouped = groupOrder.map((g) => ({ name: g, items: mainSections.filter((s) => s.group === g) }));
  const ungrouped = mainSections.filter((s) => !s.group);

  // Which group contains the currently active route (drives auto-open).
  const activeGroup = (() => {
    for (const { name, items } of grouped) {
      if (items.some((s) => s.path === location.pathname)) return name;
    }
    return null;
  })();

  const [openGroups, setOpenGroups] = useState<Set<string>>(() => {
    return new Set(activeGroup ? [activeGroup] : []);
  });

  // Keep the active group open when navigation lands on one of its pages
  // (e.g. via a link from Overview) without reopening groups the user closed.
  useEffect(() => {
    if (!activeGroup) return;
    setOpenGroups((prev) => {
      if (prev.has(activeGroup)) return prev;
      const next = new Set(prev);
      next.add(activeGroup);
      return next;
    });
  }, [activeGroup]);

  const toggleGroup = (name: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const renderItem = (section: NavSection, animateIndex: number) => {
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
        style={{ animationDelay: `${80 + animateIndex * 36}ms` }}
      >
        <span className="sidebar__icon-wrap">{section.icon}</span>
        <span className="sidebar__label">{section.label}</span>
        {label ? <span className={`sidebar__status sidebar__status--${section.status}`}>{label}</span> : null}
      </NavLink>
    );
  };

  let stagger = 0;

  return (
    <aside className={clsx("sidebar", collapsed && "sidebar--collapsed")} aria-label={navLabel}>
      <Link to="/" className="sidebar__brand" aria-label="Back to home page" data-testid="sidebar-brand-home" title="Back to home page">
        <span className="sidebar__brand-mark">FBR</span>
        <span className="sidebar__brand-name">Tax &amp; Compliance</span>
      </Link>

      <div className="sidebar__section-label" aria-hidden={collapsed}>
        <span className="eyebrow-dark">{sectionLabel}</span>
      </div>

      <nav className="sidebar__nav" data-testid={testId}>
        {ungrouped.map((section) => {
          stagger += 1;
          return renderItem(section, stagger - 1);
        })}
        {grouped.map(({ name, items }) => {
          const isOpen = openGroups.has(name);
          stagger += 1;
          return (
            <div key={name} className="sidebar__group" data-group={name}>
              <button
                type="button"
                className={clsx("sidebar__group-toggle", isOpen && "sidebar__group-toggle--open")}
                onClick={() => toggleGroup(name)}
                aria-expanded={isOpen}
                data-testid={`group-toggle-${name.toLowerCase()}`}
              >
                <span className="sidebar__group-label">{name}</span>
                <ChevronIcon className="sidebar__group-chevron" />
              </button>
              {isOpen ? <div className="sidebar__group-items">{items.map((s, i) => renderItem(s, stagger - 1 + i))}</div> : null}
            </div>
          );
        })}
      </nav>

      <div className="sidebar__footer">
        <span className="sidebar__footer-dot" aria-hidden />
        <span className="sidebar__footer-text">{footerText}</span>
        <span className="sidebar__footer-spacer" aria-hidden />
        <span className="sidebar__footer-utilities" data-testid="sidebar-utilities">
          {utilities.map((section) => (
            <NavLink
              key={section.id}
              to={section.path}
              className={({ isActive }) =>
                clsx("sidebar__utility", "sidebar__utility--footer", isActive && "sidebar__utility--active")
              }
              onClick={onClose}
              title={section.label}
              aria-label={section.label}
              data-section={section.id}
            >
              {section.icon}
            </NavLink>
          ))}
        </span>
      </div>
    </aside>
  );
}
