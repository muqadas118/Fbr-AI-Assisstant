import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar, type SidebarConfig } from "./Sidebar";
import { Header } from "./Header";
import { Main } from "./Main";
import { Notification } from "./Notification";
import { ErrorBoundary } from "./ErrorBoundary";
import { PERSONAL_SECTIONS } from "@/state/personalNav";
import { BUSINESS_SECTIONS } from "@/state/businessNav";
import { useWorkspace } from "@/state/workspace";

const SHELL_CONFIG: Record<"personal" | "business", SidebarConfig> = {
  personal: {
    sections: PERSONAL_SECTIONS,
    sectionLabel: "Personal",
    footerText: "Part 1 · Personal",
    navLabel: "Personal workspace navigation",
    testId: "personal-nav",
  },
  business: {
    sections: BUSINESS_SECTIONS,
    sectionLabel: "Business",
    footerText: "Part 2 · Business",
    navLabel: "Business workspace navigation",
    testId: "business-nav",
  },
};

export function AppShell({ variant = "personal" }: { variant?: "personal" | "business" }) {
  const config = SHELL_CONFIG[variant];
  const [collapsed, setCollapsed] = useState(false);
  // Mobile drawer (≤880px): the sidebar is an off-canvas panel there, so the
  // header toggle opens/closes it instead of collapsing a visible rail.
  const [navOpen, setNavOpen] = useState(false);

  const isMobile = () =>
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 880px)").matches;

  const toggleSidebar = () => {
    if (isMobile()) setNavOpen((v) => !v);
    else setCollapsed((c) => !c);
  };

  // The workspace follows the URL (deep links, back/forward). The store is the
  // source of truth for other readers (e.g. CalendarPage), so mirror it here
  // instead of trusting whatever navigation path wrote it last.
  const location = useLocation();
  const wsActive = useWorkspace((s) => s.active);
  useEffect(() => {
    const fromUrl = location.pathname.startsWith("/business") ? "business" : "personal";
    if (fromUrl !== wsActive) useWorkspace.getState().switchTo(fromUrl);
  }, [location.pathname, wsActive]);

  return (
    <div
      className={`app-shell ${collapsed ? "app-shell--collapsed" : ""} ${navOpen ? "app-shell--nav-open" : ""}`}
      data-testid="app-shell"
    >
      <div className="crest-band" role="banner" aria-label="Federal Board of Revenue crest band">
        <span className="crest-band__mark">FBR • ایف بی آر</span>
        <span className="crest-band__rule" aria-hidden />
        <span className="crest-band__dept">Government of Pakistan — Federal Board of Revenue</span>
        <span className="crest-band__service">Tax &amp; Compliance Assistant</span>
      </div>
      <Sidebar collapsed={collapsed} {...config} onClose={() => setNavOpen(false)} />
      <div className="app-shell__column">
        <Header onToggleSidebar={toggleSidebar} />
        <ErrorBoundary>
          <Main>
            <Outlet />
          </Main>
        </ErrorBoundary>
      </div>
      {/* Click-away backdrop for the mobile drawer (invisible on desktop). */}
      <button
        type="button"
        className="app-shell__nav-backdrop"
        aria-label="Close navigation"
        data-testid="sidebar-backdrop"
        onClick={() => setNavOpen(false)}
      />
      <Notification />
    </div>
  );
}
