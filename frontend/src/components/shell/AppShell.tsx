import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar, type SidebarConfig } from "./Sidebar";
import { Header } from "./Header";
import { Main } from "./Main";
import { Notification } from "./Notification";
import { ErrorBoundary } from "./ErrorBoundary";
import { PERSONAL_SECTIONS } from "@/state/personalNav";
import { BUSINESS_SECTIONS } from "@/state/businessNav";

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

  return (
    <div className={`app-shell ${collapsed ? "app-shell--collapsed" : ""}`} data-testid="app-shell">
      <div className="crest-band" role="banner" aria-label="Federal Board of Revenue crest band">
        <span className="crest-band__mark">FBR • ایف بی آر</span>
        <span className="crest-band__rule" aria-hidden />
        <span className="crest-band__dept">Government of Pakistan — Federal Board of Revenue</span>
        <span className="crest-band__service">Tax &amp; Compliance Assistant</span>
      </div>
      <Sidebar collapsed={collapsed} {...config} />
      <div className="app-shell__column">
        <Header onToggleSidebar={() => setCollapsed((c) => !c)} />
        <ErrorBoundary>
          <Main>
            <Outlet />
          </Main>
        </ErrorBoundary>
      </div>
      <Notification />
    </div>
  );
}
