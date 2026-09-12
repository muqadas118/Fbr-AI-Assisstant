import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { WorkspaceSwitcher } from "../components/shell/WorkspaceSwitcher";
import { useWorkspace, WORKSPACES } from "../state/workspace";
import { useNotification } from "../state/notifications";

function resetStores() {
  useWorkspace.setState({ active: "personal" });
  useNotification.setState({ current: null });
}

describe("WorkspaceSwitcher", () => {
  beforeEach(() => {
    resetStores();
  });

  it("renders both workspace options", () => {
    render(<WorkspaceSwitcher />);
    expect(screen.getByRole("button", { name: /Personal/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Business/ })).toBeInTheDocument();
  });

  it("marks Personal as active by default", () => {
    render(<WorkspaceSwitcher />);
    const personalButton = screen.getByRole("button", { name: /Personal/ });
    expect(personalButton).toHaveAttribute("aria-pressed", "true");
  });

  it("disables Business workspace when not available", () => {
    render(<WorkspaceSwitcher />);
    const businessButton = screen.getByRole("button", { name: /Business/ });
    expect(businessButton).toBeDisabled();
    expect(businessButton).toHaveAttribute("aria-disabled", "true");
    expect(businessButton).toHaveAttribute("aria-pressed", "false");
  });

  it("shows lock indicator for unavailable workspace", () => {
    render(<WorkspaceSwitcher />);
    expect(screen.getByText("Locked")).toBeInTheDocument();
  });

  it("renders with correct test id and group role", () => {
    render(<WorkspaceSwitcher />);
    const switcher = screen.getByTestId("workspace-switcher");
    expect(switcher).toHaveAttribute("role", "group");
    expect(switcher).toHaveAttribute("aria-label", "Workspace selector");
  });

  it("does not switch workspace when clicking the locked Business option", async () => {
    const user = userEvent.setup();
    render(<WorkspaceSwitcher />);
    const businessButton = screen.getByRole("button", { name: /Business/ });
    await user.click(businessButton).catch(() => {});
    expect(useWorkspace.getState().active).toBe("personal");
  });
});

describe("workspace store", () => {
  beforeEach(() => {
    resetStores();
  });

  it("starts on the personal workspace", () => {
    expect(useWorkspace.getState().active).toBe("personal");
  });

  it("refuses to switch to the locked business workspace", () => {
    const result = useWorkspace.getState().switchTo("business");
    expect(result).toBe(false);
    expect(useWorkspace.getState().active).toBe("personal");
  });

  it("describes business as unavailable and personal as available", () => {
    expect(WORKSPACES.personal.available).toBe(true);
    expect(WORKSPACES.business.available).toBe(false);
  });
});
