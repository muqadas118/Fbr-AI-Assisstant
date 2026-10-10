// ---------------------------------------------------------------------------
// Personalization panel UI state — lets any page (e.g. Settings) ask the
// assistant chat to open its "For you" panel. The panel itself lives in
// AssistantChat; this store only carries the cross-page open request.
// ---------------------------------------------------------------------------

import { create } from "zustand";

interface PersonalizationUiState {
  /** True while an open request is waiting to be consumed by the chat. */
  requested: boolean;
  requestPanel: () => void;
  clearRequest: () => void;
}

export const usePersonalizationUi = create<PersonalizationUiState>((set) => ({
  requested: false,
  requestPanel: () => set({ requested: true }),
  clearRequest: () => set({ requested: false }),
}));
