import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { InboxPage } from "@/pages/personal/InboxPage";
import { SubordinatesPage } from "@/pages/personal/SubordinatesPage";
import { WorkspacesPage } from "@/pages/personal/WorkspacesPage";

/**
 * Workspace Hub — Inbox, Subordinates, and Workspaces as internal tabs of a
 * single sidebar entry. Used by BOTH the personal and business workspaces
 * (routes /personal/workspace and /business/workspace); the active tab is
 * carried in the ?tab= query param so deep links (e.g. the header
 * Notifications button → ?tab=inbox) land on the right section.
 */

type HubTab = "inbox" | "subordinates" | "workspaces";

const TABS: { id: HubTab; label: string }[] = [
  { id: "inbox", label: "Inbox" },
  { id: "subordinates", label: "Subordinates" },
  { id: "workspaces", label: "Workspaces" },
];

function isHubTab(v: string | null): v is HubTab {
  return v === "inbox" || v === "subordinates" || v === "workspaces";
}

export function WorkspaceHubPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: HubTab = isHubTab(raw) ? raw : "inbox";

  const select = (id: HubTab) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", id);
        return next;
      },
      { replace: false },
    );
  };

  return (
    <section className="page page--workspace-hub" data-testid="workspace-hub">
      <div className="tabs page__tabs" role="tablist" aria-label="Workspace hub sections" data-testid="hub-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={clsx("tab-btn", tab === t.id && "tab-btn--active")}
            onClick={() => select(t.id)}
            data-testid={`hub-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="hub__content" role="tabpanel" aria-label={tab} data-testid="hub-panel">
        {tab === "inbox" ? (
          <InboxPage />
        ) : tab === "subordinates" ? (
          <SubordinatesPage />
        ) : (
          <WorkspacesPage />
        )}
      </div>
    </section>
  );
}
