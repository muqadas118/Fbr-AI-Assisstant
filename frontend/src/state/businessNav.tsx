// ---------------------------------------------------------------------------
// Business workspace navigation. Mirrors the 14 business experience pages
// (Overview, Assistant, Calculator, Tax Reducer, Invoices, Documents, Notices,
// Compliance Calendar, Return Readiness, Tax Health, Verification, Tax Vault,
// Team, Compliance Monitor).
// ---------------------------------------------------------------------------

import type { ReactNode } from "react";

export interface BusinessSection {
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

export const BUSINESS_SECTIONS: BusinessSection[] = [
  {
    id: "overview",
    label: "Overview",
    blurb: "Business status, upcoming deadlines, and recent activity.",
    path: "/business/overview",
    status: "ready",
    icon: icon("M3 12l9-9 9 9M5 10v10h14V10"),
  },
  {
    id: "assistant",
    label: "AI Tax Assistant",
    blurb: "Natural-language questions about FBR business tax and compliance.",
    path: "/business/assistant",
    status: "ready",
    icon: icon("M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"),
  },
  {
    id: "calculator",
    label: "Business Tax Calculator",
    blurb: "Calculate business tax using the verified backend pipeline.",
    path: "/business/calculator",
    status: "ready",
    icon: icon("M4 4h16v4H4zM4 12h7M4 16h7M4 20h7M15 12h5M15 16h5M15 20h5"),
  },
  {
    id: "tax-reducer",
    label: "Tax Reducer",
    blurb: "Find lawful ways to reduce your business tax liability.",
    path: "/business/tax-reducer",
    status: "ready",
    icon: icon("M3 7l6 6 4-4 7 7M14 16h6v-6"),
  },
  {
    id: "invoices",
    label: "Business Invoices",
    blurb: "Business invoice workspace (processing and reconciliation).",
    path: "/business/invoices",
    status: "ready",
    icon: icon("M4 4h12l4 4v12H4zM4 9h16M9 14h6M9 18h6"),
  },
  {
    id: "documents",
    label: "Business Documents",
    blurb: "Business tax document library and analysis.",
    path: "/business/documents",
    status: "ready",
    icon: icon("M6 3h9l5 5v13H6zM15 3v5h5M9 13h6M9 17h6"),
  },
  {
    id: "notices",
    label: "FBR Notices",
    blurb: "Upload and analyze FBR notices for business entities.",
    path: "/business/notices",
    status: "ready",
    icon: icon("M3 7l9 6 9-6M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7M3 7l9-4 9 4"),
  },
  {
    id: "calendar",
    label: "Compliance Calendar",
    blurb: "Upcoming business tax deadlines and calendar events.",
    path: "/business/calendar",
    status: "ready",
    icon: icon("M3 4h18v4H3zM5 8v12h14V8M9 12v4M15 12v4"),
  },
  {
    id: "readiness",
    label: "Return Readiness",
    blurb: "Whether business returns can be filed today.",
    path: "/business/readiness",
    status: "ready",
    icon: icon("M4 12l5 5L20 6M4 19h16"),
  },
  {
    id: "health",
    label: "Tax Health",
    blurb: "Business compliance signals and integrity checks.",
    path: "/business/health",
    status: "ready",
    icon: icon("M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0zM12 7v5l3 3"),
  },
  {
    id: "verification",
    label: "Verification",
    blurb: "How backend answers are verified for business queries.",
    path: "/business/verification",
    status: "ready",
    icon: icon("M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6zM9 12l2 2 4-4"),
  },
  {
    id: "vault",
    label: "Business Tax Vault",
    blurb: "Your business tax document store.",
    path: "/business/vault",
    status: "ready",
    icon: icon("M6 3h12v4H6zM6 7v14h12V7M10 11v6M14 11v6"),
  },
  {
    id: "team",
    label: "Team",
    blurb: "Manage team members, roles, and access for your business.",
    path: "/business/team",
    status: "ready",
    icon: icon("M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"),
  },
  {
    id: "monitor",
    label: "Compliance Monitor",
    blurb: "Live monitoring of business filings, refunds, and compliance risk.",
    path: "/business/monitor",
    status: "ready",
    icon: icon("M22 12h-4l-3 9L9 3l-3 9H2"),
  },
];

export function findBusinessSectionByPath(path: string): BusinessSection | undefined {
  return BUSINESS_SECTIONS.find((s) => s.path === path);
}
