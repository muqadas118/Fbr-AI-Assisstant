import clsx from "clsx";
import { useNavigate } from "react-router-dom";
import { useNotification } from "@/state/notifications";
import { WORKSPACES, useWorkspace, type WorkspaceId } from "@/state/workspace";

export function WorkspaceSwitcher() {
  const active = useWorkspace((s) => s.active);
  const switchTo = useWorkspace((s) => s.switchTo);
  const notify = useNotification((s) => s.show);
  const navigate = useNavigate();

  const handle = (target: WorkspaceId) => {
    if (target === active) return;
    const ok = switchTo(target);
    if (!ok) {
      const desc = WORKSPACES[target];
      notify("warn", `${desc.label} workspace is not enabled yet. Coming in a later release.`);
      return;
    }
    // Both workspaces are live — land the user on its overview.
    navigate(`/${target}/overview`);
  };

  return (
    <div
      className="ws-switch"
      role="group"
      aria-label="Workspace selector"
      data-testid="workspace-switcher"
    >
      {(Object.keys(WORKSPACES) as WorkspaceId[]).map((id) => {
        const ws = WORKSPACES[id];
        const isActive = id === active;
        return (
          <button
            key={id}
            type="button"
            className={clsx("ws-switch__opt", isActive && "ws-switch__opt--active")}
            aria-pressed={isActive}
            aria-disabled={!ws.available && !isActive}
            disabled={!ws.available && !isActive}
            onClick={() => handle(id)}
            title={ws.description}
            data-workspace={id}
          >
            <span className="ws-switch__dot" />
            <span className="ws-switch__label">{ws.label}</span>
            {!ws.available ? <span className="ws-switch__lock" aria-label="Locked">Locked</span> : null}
          </button>
        );
      })}
    </div>
  );
}