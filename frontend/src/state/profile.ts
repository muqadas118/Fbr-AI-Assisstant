// ---------------------------------------------------------------------------
// Profile store — shared identity (NTN/CNIC/email/displayName) persisted to
// localStorage. Single source of truth replacing the scattered `fbr_ntn`
// localStorage hack. Readers keep a localStorage fallback so existing saved
// values survive the migration.
// ---------------------------------------------------------------------------

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ProfileState {
  ntn: string;
  cnic: string;
  email: string;
  displayName: string;
  setProfile: (patch: Partial<Pick<ProfileState, "ntn" | "cnic" | "email" | "displayName">>) => void;
  setNtn: (ntn: string) => void;
  setCnic: (cnic: string) => void;
  setEmail: (email: string) => void;
  setDisplayName: (displayName: string) => void;
  clear: () => void;
}

function readLegacyNtn(): string {
  try {
    return localStorage.getItem("fbr_ntn") ?? "";
  } catch {
    return "";
  }
}

function readLegacyDisplayName(): string {
  try {
    const raw = localStorage.getItem("fbr-settings");
    if (!raw) return "";
    const parsed = JSON.parse(raw) as { displayName?: unknown };
    return typeof parsed.displayName === "string" ? parsed.displayName : "";
  } catch {
    return "";
  }
}

function syncLegacyNtn(ntn: string): void {
  try {
    if (ntn) localStorage.setItem("fbr_ntn", ntn);
    else localStorage.removeItem("fbr_ntn");
  } catch {
    // Non-fatal: persist middleware still holds the value.
  }
}

export const useProfile = create<ProfileState>()(
  persist(
    (set) => ({
      ntn: typeof localStorage !== "undefined" ? readLegacyNtn() : "",
      cnic: "",
      email: "",
      displayName: typeof localStorage !== "undefined" ? readLegacyDisplayName() : "",
      setProfile: (patch) =>
        set((s) => {
          const next = { ...s, ...patch };
          if (patch.ntn !== undefined) syncLegacyNtn(patch.ntn);
          return next;
        }),
      setNtn: (ntn) => {
        syncLegacyNtn(ntn);
        set({ ntn });
      },
      setCnic: (cnic) => set({ cnic }),
      setEmail: (email) => set({ email }),
      setDisplayName: (displayName) => set({ displayName }),
      clear: () => {
        syncLegacyNtn("");
        set({ ntn: "", cnic: "", email: "", displayName: "" });
      },
    }),
    {
      name: "fbr-profile",
      partialize: (s) => ({
        ntn: s.ntn,
        cnic: s.cnic,
        email: s.email,
        displayName: s.displayName,
      }),
    },
  ),
);

// Migration-safe read: store first, legacy `fbr_ntn` key as fallback.
export function getEffectiveNtn(): string {
  try {
    const fromStore = useProfile.getState().ntn;
    if (fromStore) return fromStore;
    return localStorage.getItem("fbr_ntn") ?? "";
  } catch {
    return useProfile.getState().ntn ?? "";
  }
}
