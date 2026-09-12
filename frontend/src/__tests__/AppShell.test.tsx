import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../components/shell/AppShell";
import { Header } from "../components/shell/Header";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      health: vi.fn(),
      answer: vi.fn(),
    },
  };
});

describe("AppShell", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../lib/api");
    vi.mocked(api.health).mockResolvedValue({ status: "ok", version: "1.0.0" });
  });

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

  it("shows API connected status when backend is healthy", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    await screen.findByText("API Connected");
    expect(screen.getByText("API Connected")).toBeInTheDocument();
  });

  it("shows API offline status when backend is unavailable", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.health).mockRejectedValue(new Error("API Down"));
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    await screen.findByText("API Offline");
    expect(screen.getByText("API Offline")).toBeInTheDocument();
  });

  it("renders all 14 personal navigation sections", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    const items = nav.querySelectorAll(".sidebar__item");
    expect(items.length).toBe(14);
  });

  it("renders section status badges (Stub/Preview)", async () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <AppShell />
      </MemoryRouter>,
    );
    const nav = screen.getByTestId("personal-nav");
    expect(nav.textContent).toContain("Stub");
    expect(nav.textContent).toContain("Preview");
  });
});

describe("Header", () => {
  it("renders with default props", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} apiHealthy={null} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("sidebar-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("api-status")).toBeInTheDocument();
  });

  it("shows API unknown status initially", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} apiHealthy={null} />
      </MemoryRouter>,
    );
    expect(screen.getByText("API ?")).toBeInTheDocument();
  });

  it("shows API connected when healthy", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} apiHealthy={true} />
      </MemoryRouter>,
    );
    expect(screen.getByText("API Connected")).toBeInTheDocument();
  });

  it("shows API offline when unhealthy", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} apiHealthy={false} />
      </MemoryRouter>,
    );
    expect(screen.getByText("API Offline")).toBeInTheDocument();
  });

  it("displays the workspace pill", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} apiHealthy={true} />
      </MemoryRouter>,
    );
    const pill = container.querySelector(".app-header__workspace-pill");
    expect(pill).toBeTruthy();
    expect(pill?.textContent).toBe("Personal");
  });

  it("displays notifications button", () => {
    render(
      <MemoryRouter initialEntries={["/personal/overview"]}>
        <Header onToggleSidebar={() => {}} apiHealthy={true} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });
});
