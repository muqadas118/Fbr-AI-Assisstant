// ---------------------------------------------------------------------------
// Workspace state — personal / business switcher. Both workspaces are live:
// Personal (Part 1) and Business (Part 2). Routes live in App.tsx.
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
  switchTo: (target: WorkspaceId) => boolean; // returns true if switched
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  active: "personal",
  switchTo: (target) => {
    if (!WORKSPACES[target].available) {
      return false;
    }
    set({ active: target });
    return true;
  },
}));
