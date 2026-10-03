import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../components/shell/AppShell";
import { PERSONAL_SECTIONS } from "../state/personalNav";
import { BUSINESS_SECTIONS } from "../state/businessNav";
import { WorkspaceHubPage } from "../pages/workspace/WorkspaceHubPage";
import { ResearchPage } from "../pages/personal/ResearchPage";

// Backend-backed pages: network is never contacted during these render
// smoke tests, but the api module still initializes — stub its transport.
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: Object.assign(actual.api, {
      answer: vi.fn().mockRejectedValue(new Error("offline test")),
      monitor: {
        ...actual.api.monitor,
        getDashboard: vi.fn().mockRejectedValue(new Error("offline test")),
        subscribe: vi.fn().mockRejectedValue(new Error("offline test")),
        simulateNotice: vi.fn().mockRejectedValue(new Error("offline test")),
      },
      team: {
        ...actual.api.team,
        getUserDashboard: vi.fn().mockRejectedValue(new Error("offline test")),
        getTeamDashboard: vi.fn().mockRejectedValue(new Error("offline test")),
        getRoles: vi.fn().mockRejectedValue(new Error("offline test")),
      },
      workspaces: {
        ...actual.api.workspaces,
        get: vi.fn().mockRejectedValue(new Error("offline test")),
        createWorkspace: vi.fn().mockRejectedValue(new Error("offline test")),
      },
      calendar: {
        ...actual.api.calendar,
        getDashboard: vi.fn().mockRejectedValue(new Error("offline test")),
        getUpcoming: vi.fn().mockRejectedValue(new Error("offline test")),
      },
    }),
  };
});

function renderAt(path: string, ui: React.ReactElement) {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
}

describe("Workspace Hub", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders the three hub tabs with Inbox active by default", () => {
    renderAt("/business/workspace", <WorkspaceHubPage />);
    expect(screen.getByTestId("hub-tabs")).toBeInTheDocument();
    expect(screen.getByTestId("hub-tab-inbox")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("inbox-setup")).toBeInTheDocument();
  });

  it("switches to Subordinates and Workspaces via the hub tabs", async () => {
    const user = userEvent.setup();
    renderAt("/personal/workspace", <WorkspaceHubPage />);

    await user.click(screen.getByTestId("hub-tab-subordinates"));
    expect(screen.getByTestId("hub-tab-subordinates")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("sub-setup")).toBeInTheDocument();

    await user.click(screen.getByTestId("hub-tab-workspaces"));
    expect(screen.getByTestId("hub-tab-workspaces")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("ws-setup")).toBeInTheDocument();
    expect(screen.getByTestId("ws-user-id-input")).toBeInTheDocument();
  });

  it("deep-links ?tab=workspaces straight onto that tab", () => {
    renderAt("/personal/workspace?tab=workspaces", <WorkspaceHubPage />);
    expect(screen.getByTestId("hub-tab-workspaces")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("ws-user-id-input")).toBeInTheDocument();
  });

  it("auto-loads the inbox identity (stable demo id when signed out)", () => {
    renderAt("/personal/workspace?tab=inbox", <WorkspaceHubPage />);
    const input = screen.getByTestId("inbox-user-id-input") as HTMLInputElement;
    expect(input.value).not.toBe("");
    expect(input.value).toMatch(/^demo-/);
  });
});

describe("Business parity", () => {
  it("renders Research under /business/research", () => {
    renderAt("/business/research", <ResearchPage />);
    expect(screen.getByText("FBR Research & Updates")).toBeInTheDocument();
    expect(screen.getByTestId("research-input")).toBeInTheDocument();
  });
});

describe("Sidebar parity", () => {
  it("both sidebars expose the single Workspace Hub entry", async () => {
    const user = userEvent.setup();

    renderAt("/business/overview", <AppShell variant="business" />);
    const nav = screen.getByTestId("business-nav");
    for (const toggle of Array.from(nav.querySelectorAll<HTMLButtonElement>(".sidebar__group-toggle"))) {
      await user.click(toggle);
    }
    expect(nav.querySelector('[data-section="workspace-hub"]')).toBeTruthy();
    expect(nav.querySelector('[data-group="Workspace"] [data-section="workspace-hub"]')).toBeTruthy();
    // Flat entries are gone.
    expect(nav.querySelector('[data-section="inbox"]')).toBeNull();
    expect(nav.querySelector('[data-section="subordinates"]')).toBeNull();
    expect(nav.querySelector('[data-section="workspaces"]')).toBeNull();
    // Business extras remain.
    expect(nav.querySelector('[data-section="team"]')).toBeTruthy();
    expect(nav.querySelector('[data-section="monitor"]')).toBeTruthy();
  });

  it("personal sidebar also shows the hub under Workspace", async () => {
    const user = userEvent.setup();
    renderAt("/personal/overview", <AppShell />);
    const nav = screen.getByTestId("personal-nav");
    for (const toggle of Array.from(nav.querySelectorAll<HTMLButtonElement>(".sidebar__group-toggle"))) {
      await user.click(toggle);
    }
    expect(nav.querySelector('[data-section="workspace-hub"]')).toBeTruthy();
  });

  it("every personal feature exists in business, and business has extras", () => {
    const personalIds = PERSONAL_SECTIONS.map((s) => s.id);
    const businessIds = BUSINESS_SECTIONS.map((s) => s.id);

    for (const id of personalIds) {
      expect(businessIds).toContain(id);
    }
    const extras = businessIds.filter((id) => !personalIds.includes(id));
    expect(extras.sort()).toEqual(["monitor", "team"].sort());
    expect(BUSINESS_SECTIONS.length).toBe(PERSONAL_SECTIONS.length + 2);
  });

  it("personal verification is no longer a stub", () => {
    expect(PERSONAL_SECTIONS.find((s) => s.id === "verification")?.status).toBe("ready");
    expect(BUSINESS_SECTIONS.filter((s) => s.status === "stub").length).toBe(0);
  });
});
