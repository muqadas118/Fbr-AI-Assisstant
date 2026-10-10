// ---------------------------------------------------------------------------
// Assistant chat activity — the assistant pages hide their big page header
// once a conversation has started (ChatGPT-style: title fades, chat takes the
// viewport). AssistantChat owns the state; the pages only read it.
// ---------------------------------------------------------------------------

import { create } from "zustand";

interface ChatActiveState {
  /** True while the chat has at least one message in the conversation. */
  active: boolean;
  setActive: (active: boolean) => void;
}

export const useChatActive = create<ChatActiveState>((set) => ({
  active: false,
  setActive: (active) => set({ active }),
}));
