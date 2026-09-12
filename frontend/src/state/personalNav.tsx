// ---------------------------------------------------------------------------
// Personal workspace navigation. Single source of truth — drives the sidebar,
// the route table, and any "current section" indicator.
// ---------------------------------------------------------------------------

import type { ReactNode } from "react";

export interface PersonalSection {
  id: string;
  label: string;
  blurb: string;
  path: string;
  icon: ReactNode;
  status: "ready" | "partial" | "stub";
}

const icon = (path: string) => (
  <svg
    className="sidebar__icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
  >
    <path d={path} />
  </svg>
);

export const PERSONAL_SECTIONS: PersonalSection[] = [
  {
    id: "overview",
    label: "Overview",
    blurb: "Status, upcoming deadlines, recent activity.",
    path: "/personal/overview",
    status: "stub",
    icon: icon("M3 12l9-9 9 9M5 10v10h14V10"),
  },
  {
    id: "assistant",
    label: "AI Tax Assistant",
    blurb: "Natural-language questions about FBR tax and compliance.",
    path: "/personal/assistant",
    status: "ready",
    icon: icon("M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"),
  },
  {
    id: "calculator",
    label: "Tax Calculator",
    blurb: "Calculate tax using the verified backend pipeline.",
    path: "/personal/calculator",
    status: "ready",
    icon: icon("M4 4h16v4H4zM4 12h7M4 16h7M4 20h7M15 12h5M15 16h5M15 20h5"),
  },
  {
    id: "tax-reducer",
    label: "Tax Reducer",
    blurb: "Find lawful ways to reduce your tax liability.",
    path: "/personal/tax-reducer",
    status: "ready",
    icon: icon("M3 7l6 6 4-4 7 7M14 16h6v-6"),
  },
  {
    id: "invoices",
    label: "My Invoices",
    blurb: "Personal invoice workspace (preparation UI).",
    path: "/personal/invoices",
    status: "stub",
    icon: icon("M4 4h12l4 4v12H4zM4 9h16M9 14h6M9 18h6"),
  },
  {
    id: "documents",
    label: "Documents",
    blurb: "Personal tax document library.",
    path: "/personal/documents",
    status: "stub",
    icon: icon("M6 3h9l5 5v13H6zM15 3v5h5M9 13h6M9 17h6"),
  },
  {
    id: "notices",
    label: "FBR Notices",
    blurb: "Upload and analyze an FBR notice.",
    path: "/personal/notices",
    status: "partial",
    icon: icon("M3 7l9 6 9-6M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7M3 7l9-4 9 4"),
  },
  {
    id: "calendar",
    label: "Compliance Calendar",
    blurb: "Upcoming personal tax deadlines.",
    path: "/personal/calendar",
    status: "stub",
    icon: icon("M3 4h18v4H3zM5 8v12h14V8M9 12v4M15 12v4"),
  },
  {
    id: "readiness",
    label: "Return Readiness",
    blurb: "Whether your personal return can be filed today.",
    path: "/personal/readiness",
    status: "stub",
    icon: icon("M4 12l5 5L20 6M4 19h16"),
  },
  {
    id: "health",
    label: "Tax Health",
    blurb: "Compliance signals and integrity checks.",
    path: "/personal/health",
    status: "stub",
    icon: icon("M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0zM12 7v5l3 3"),
  },
  {
    id: "verification",
    label: "Verification",
    blurb: "How a backend answer was verified.",
    path: "/personal/verification",
    status: "ready",
    icon: icon("M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6zM9 12l2 2 4-4"),
  },
  {
    id: "vault",
    label: "Tax Vault",
    blurb: "Your personal tax document store.",
    path: "/personal/vault",
    status: "stub",
    icon: icon("M6 3h12v4H6zM6 7v14h12V7M10 11v6M14 11v6"),
  },
  {
    id: "research",
    label: "Research & Updates",
    blurb: "FBR updates, circulars, and current information.",
    path: "/personal/research",
    status: "partial",
    icon: icon("M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4zM8 8h8M8 12h8M8 16h5"),
  },
  {
    id: "settings",
    label: "Profile / Settings",
    blurb: "Display and notification preferences.",
    path: "/personal/settings",
    status: "ready",
    icon: icon("M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM19 12a7 7 0 0 0-.1-1.2l2.1-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.6 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4L5.1 10.8A7 7 0 0 0 5 12a7 7 0 0 0 .1 1.2L3 14.8l2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.6-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2.1-1.6A7 7 0 0 0 19 12z"),
  },
  {
    id: "inbox",
    label: "Inbox",
    blurb: "Unified inbox for notices, messages, and alerts.",
    path: "/personal/inbox",
    status: "ready",
    icon: icon("M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm0 2v12h16V6H4zm8 14H4V8h16v12z"),
  },
  {
    id: "subordinates",
    label: "Subordinates",
    blurb: "Manage and oversee subordinate tax profiles.",
    path: "/personal/subordinates",
    status: "ready",
    icon: icon("M12 5v2M12 17v2M5 12h2M17 12h2M5 5l2 2m10 0l-2 2M5 19l2-2m10 0l-2-2M12 12l5 5M7 7l5 5M12 12l-5 5M7 17l5-5"),
  },
  {
    id: "workspaces",
    label: "Workspaces",
    blurb: "Collaborative workspaces for tax teams.",
    path: "/personal/workspaces",
    status: "ready",
    icon: icon("M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"),
  },
];

export function findSectionByPath(path: string): PersonalSection | undefined {
  return PERSONAL_SECTIONS.find((s) => s.path === path);
}
