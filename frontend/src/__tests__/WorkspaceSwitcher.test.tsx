import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { WorkspaceSwitcher } from "../components/shell/WorkspaceSwitcher";
import { useWorkspace, WORKSPACES } from "../state/workspace";
import { useNotification } from "../state/notifications";

const initialSwitchTo = useWorkspace.getState().switchTo;

function resetStores() {
  useWorkspace.setState({ active: "personal", switchTo: initialSwitchTo });
  useNotification.setState({ current: null });
}

function renderSwitcher(initialEntry = "/personal/overview") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <WorkspaceSwitcher />
    </MemoryRouter>,
  );
}

describe("WorkspaceSwitcher", () => {
  beforeEach(() => {
    resetStores();
  });

  it("renders both workspace options", () => {
    renderSwitcher();
    expect(screen.getByRole("button", { name: /Personal/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Business/ })).toBeInTheDocument();
  });

  it("marks Personal as active by default", () => {
    renderSwitcher();
    const personalButton = screen.getByRole("button", { name: /Personal/ });
    expect(personalButton).toHaveAttribute("aria-pressed", "true");
  });

  it("enables Business workspace when available", () => {
    renderSwitcher();
    const businessButton = screen.getByRole("button", { name: /Business/ });
    expect(businessButton).not.toBeDisabled();
    expect(businessButton).toHaveAttribute("aria-disabled", "false");
    expect(businessButton).toHaveAttribute("aria-pressed", "false");
  });

  it("shows no lock indicator when all workspaces are available", () => {
    renderSwitcher();
    expect(screen.queryByText("Locked")).not.toBeInTheDocument();
  });

  it("renders with correct test id and group role", () => {
    renderSwitcher();
    const switcher = screen.getByTestId("workspace-switcher");
    expect(switcher).toHaveAttribute("role", "group");
    expect(switcher).toHaveAttribute("aria-label", "Workspace selector");
  });

  it("switches to Business when clicking the Business option", async () => {
    const user = userEvent.setup();
    renderSwitcher();
    const businessButton = screen.getByRole("button", { name: /Business/ });
    await user.click(businessButton);
    expect(useWorkspace.getState().active).toBe("business");
    expect(useNotification.getState().current).toBeNull();
  });

  it("shows warning toast when switching fails", async () => {
    const user = userEvent.setup();
    const original = useWorkspace.getState().switchTo;
    useWorkspace.setState({ switchTo: () => false });
    try {
      renderSwitcher();
      const businessButton = screen.getByRole("button", { name: /Business/ });
      await user.click(businessButton);
      expect(useWorkspace.getState().active).toBe("personal");
      const current = useNotification.getState().current;
      expect(current).not.toBeNull();
      expect(current?.kind).toBe("warn");
      expect(current?.message).toContain("Business");
    } finally {
      useWorkspace.setState({ switchTo: original });
    }
  });

  it("does nothing when clicking the already-active workspace", async () => {
    const user = userEvent.setup();
    renderSwitcher();
    const personalButton = screen.getByRole("button", { name: /Personal/ });
    await user.click(personalButton);
    expect(useWorkspace.getState().active).toBe("personal");
    expect(useNotification.getState().current).toBeNull();
  });
});

describe("workspace store", () => {
  beforeEach(() => {
    resetStores();
  });

  it("starts on the personal workspace", () => {
    expect(useWorkspace.getState().active).toBe("personal");
  });

  it("switches to the business workspace when available", () => {
    const result = useWorkspace.getState().switchTo("business");
    expect(result).toBe(true);
    expect(useWorkspace.getState().active).toBe("business");
  });

  it("describes both workspaces as available", () => {
    expect(WORKSPACES.personal.available).toBe(true);
    expect(WORKSPACES.business.available).toBe(true);
  });
});
