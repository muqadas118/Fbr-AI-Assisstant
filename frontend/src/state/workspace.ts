// ---------------------------------------------------------------------------
// Workspace state — personal / business switcher. Both workspaces are live:
// Personal (Part 1) and Business (Part 2). Routes live in App.tsx.
//
// Gating: signup onboarding allocates ONE primary workspace
// (preferred_workspace on the backend user row). The shell then only offers
// that workspace — doosri workspace nazar nahi aati (jaise normal websites
// par hota hai). allowed === null means "sab allowed" (pre-onboarding or
// legacy sessions).
// ---------------------------------------------------------------------------

import { create } from "zustand";

export type WorkspaceId = "personal" | "business";

export interface WorkspaceDescriptor {
  id: WorkspaceId;
  label: string;
  description: string;
  available: boolean;
}

export const WORKSPACES: Record<WorkspaceId, WorkspaceDescriptor> = {
  personal: {
    id: "personal",
    label: "Personal",
    description: "Individual filings, notice analysis, personal research.",
    available: true,
  },
  business: {
    id: "business",
    label: "Business",
    description: "Organizations, team workflow, and entity filings.",
    available: true,
  },
};

interface WorkspaceState {
  active: WorkspaceId;
  /** Allocated primary workspace; null = both visible (no allocation yet). */
  allowed: WorkspaceId | null;
  setAllowed: (ws: WorkspaceId | null) => void;
  isAllowed: (target: WorkspaceId) => boolean;
  switchTo: (target: WorkspaceId) => boolean; // returns true if switched
}

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  active: "personal",
  allowed: null,

  setAllowed: (ws) => set({ allowed: ws, active: ws ?? get().active }),

  isAllowed: (target) => {
    const allowed = get().allowed;
    return allowed === null || allowed === target;
  },

  switchTo: (target) => {
    if (!WORKSPACES[target].available) {
      return false;
    }
    // Gating: allocated workspace ke ilawa switch manaa hai.
    if (!get().isAllowed(target)) {
      return false;
    }
    set({ active: target });
    return true;
  },
}));

/** Reactive-safe read for render paths (module consumers). */
export function isWorkspaceVisible(ws: WorkspaceId): boolean {
  return useWorkspace.getState().isAllowed(ws);
}
