// ---------------------------------------------------------------------------
// Lightweight toast/notification store (no third-party UI library).
// ---------------------------------------------------------------------------

import { create } from "zustand";

export type NotificationKind = "info" | "ok" | "warn" | "err";

export interface Notification {
  id: number;
  kind: NotificationKind;
  message: string;
}

interface NotificationState {
  current: Notification | null;
  show: (kind: NotificationKind, message: string) => void;
  dismiss: () => void;
}

let counter = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

export const useNotification = create<NotificationState>((set) => ({
  current: null,
  show: (kind, message) => {
    counter += 1;
    if (timer) {
      clearTimeout(timer);
    }
    set({ current: { id: counter, kind, message } });
    timer = setTimeout(() => {
      set({ current: null });
      timer = null;
    }, 4500);
  },
  dismiss: () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    set({ current: null });
  },
}));
