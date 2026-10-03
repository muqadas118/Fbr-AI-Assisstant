import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../components/shell/AppShell";
import { Header } from "../components/shell/Header";
import { PERSONAL_SECTIONS } from "../state/personalNav";

describe("AppShell", () => {
  it("renders the app shell without crashing", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(document.querySelector('[data-testid="app-shell"]')).toBeTruthy();
  });

  it("renders the sidebar navigation", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("personal-nav")).toBeTruthy();
  });

  it("renders the workspace switcher", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("workspace-switcher")).toBeTruthy();
  });

  it("renders the sidebar toggle button", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("sidebar-toggle")).toBeTruthy();
  });

  it("renders header with current section title", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
  });

  it("keeps the header free of backend status clutter", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("api-status")).toBeNull();
    expect(screen.queryByText("API Connected")).toBeNull();
    expect(screen.queryByText("API Offline")).toBeNull();
  });

  it("renders all 17 personal navigation sections", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    // Open every group dropdown, then every section should be in the DOM.
    for (const toggle of Array.from(nav.querySelectorAll<HTMLButtonElement>(".sidebar__group-toggle"))) {
      await user.click(toggle);
    }
    const items = nav.querySelectorAll(".sidebar__item");
    const utilities = screen.getByTestId("sidebar-utilities").querySelectorAll(".sidebar__utility");
    // Bottom utilities (Profile / Settings) render as icons, not nav rows.
    expect(items.length).toBe(PERSONAL_SECTIONS.length - utilities.length);
    expect(items.length + utilities.length).toBe(PERSONAL_SECTIONS.length);
    for (const section of PERSONAL_SECTIONS) {
      const inNav = nav.querySelector(`[data-section="${section.id}"]`);
      const inUtilities = screen
        .getByTestId("sidebar-utilities")
        .querySelector(`[data-section="${section.id}"]`);
      expect(inNav ?? inUtilities).toBeTruthy();
    }
  });

  it("keeps group dropdowns closed until the user opens them", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    // Ungrouped rows (Overview + AI Tax Assistant) are always visible; group items stay hidden.
    expect(nav.querySelectorAll(".sidebar__item").length).toBe(2);
    expect(nav.textContent).toContain("AI Tax Assistant");
    expect(nav.textContent).toContain("Calculators");
    expect(nav.querySelector('[data-section="calculator"]')).toBeNull();

    await user.click(screen.getByTestId("group-toggle-calculators"));
    expect(nav.querySelector('[data-section="calculator"]')).toBeTruthy();
    expect(nav.querySelector('[data-section="tax-reducer"]')).toBeTruthy();

    await user.click(screen.getByTestId("group-toggle-calculators"));
    expect(nav.querySelector('[data-section="calculator"]')).toBeNull();
  });

  it("auto-opens the group containing the active route", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/calculator"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    expect(nav.querySelector('[data-section="calculator"]')).toBeTruthy();
    expect(nav.querySelector('[data-section="tax-reducer"]')).toBeTruthy();
    // Unrelated groups remain closed.
    expect(nav.querySelector('[data-section="invoices"]')).toBeNull();
  });

  it("groups similar sections under shared headings", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    expect(nav.textContent).toContain("Calculators");
    await user.click(screen.getByTestId("group-toggle-calculators"));
    expect(nav.querySelector('[data-group="Calculators"] .sidebar__item[data-section="calculator"]')).toBeTruthy();
    expect(nav.querySelector('[data-group="Calculators"] .sidebar__item[data-section="tax-reducer"]')).toBeTruthy();
    expect(nav.textContent).toContain("Records");
    expect(nav.textContent).toContain("Compliance");
  });

  it("renders Profile / Settings as a bottom utility icon", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    expect(nav.querySelector('[data-section="settings"]')).toBeNull();
    const utility = screen.getByRole("link", { name: "Profile / Settings" });
    expect(utility.getAttribute("href")).toBe("/personal/settings");
    expect(utility.className).toContain("sidebar__utility");
  });

  it("renders section status badges (Stub only in nav)", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    // Open all groups to see every badge.
    for (const toggle of Array.from(nav.querySelectorAll<HTMLButtonElement>(".sidebar__group-toggle"))) {
      await user.click(toggle);
    }
    // Verification went live in the workspace-parity pass — the nav is now
    // fully "ready". Profile / Settings is a stub but lives in the bottom
    // utility row, which carries no badge.
    const expectedStub = PERSONAL_SECTIONS.filter((s) => s.status === "stub" && !s.bottomUtility).length;
    const expectedPreview = PERSONAL_SECTIONS.filter((s) => s.status === "partial").length;
    expect(expectedStub).toBe(0);
    expect(expectedPreview).toBe(0);
    expect(nav.textContent).not.toContain("Stub");
    expect(nav.querySelectorAll(".sidebar__status--stub").length).toBe(expectedStub);
    expect(nav.querySelectorAll(".sidebar__status--partial").length).toBe(expectedPreview);
    expect(nav.querySelectorAll(".sidebar__status").length).toBe(expectedStub + expectedPreview);
  });
});

describe("Header", () => {
  it("renders with default props", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("sidebar-toggle")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
  });

  it("shows no backend status badge or clutter", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("api-status")).toBeNull();
    expect(screen.queryByText(/API /)).toBeNull();
  });

  it("displays the workspace pill", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} />
      </MemoryRouter>,
    );
    const pill = container.querySelector(".app-header__workspace-pill");
    expect(pill).toBeTruthy();
    expect(pill?.textContent).toBe("Personal");
  });

  it("displays notifications button", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });
});
