// ---------------------------------------------------------------------------
// Onboarding store — signup questionnaire + workspace allocation.
//
// Flow (normal websites jaisa):
//   signup → questionnaire ("What brings you here?") → answers drive a
//   recommended primary workspace → POST /auth/workspace persists it →
//   user lands in that workspace with a completion banner.
//
// The workspace decision is persisted on the backend user row
// (preferred_workspace) so it survives reloads and restarts. The active
// flag mirrors it into the workspace store; the sandbox persisted copy
// (fbr-onboarding-v1) only records ONBOARDING COMPLETION for gating.
// ---------------------------------------------------------------------------

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authApi, isUnauthorized } from "@/lib/api";
import { getStoredAuthToken, useAuth } from "@/state/auth";
import { useWorkspace } from "@/state/workspace";

export type OnboardingOutcome = "personal" | "business";

export interface QuestionOption {
  id: string;
  label: string;
  blurb: string;
}

export interface Question {
  id: string;
  title: string;
  options: QuestionOption[];
}

/** The signup questionnaire — one screen of choices, no typing required. */
export const ONBOARDING_QUESTIONS: Question[] = [
  {
    id: "account_for",
    title: "Aap kis ke liye account bana rahe hain?",
    options: [
      { id: "individual", label: "Myself (individual)", blurb: "Salary, personal income tax, notices." },
      { id: "business", label: "A business / company", blurb: "Sales tax, withholding, team filings." },
    ],
  },
  {
    id: "main_use",
    title: "Sab se zyada kaam kya ka? (main use)",
    options: [
      { id: "answers", label: "Tax sawal ka jawab", blurb: "AI assistant with cited answers." },
      { id: "calculations", label: "Calculations aur returns", blurb: "Calculator, readiness, filing deadlines." },
      { id: "records", label: "Record-keeping", blurb: "Invoices, documents, notices in one vault." },
    ],
  },
  {
    id: "filing_frequency",
    title: "Filing kitni aksar hogi?",
    options: [
      { id: "annual", label: "Saal me ek bar", blurb: "Annual income tax return." },
      { id: "monthly", label: "Har mahine", blurb: "Monthly sales tax / WHT statements." },
    ],
  },
];

interface OnboardingState {
  /** Question answers keyed by question id (option id). */
  answers: Record<string, string>;
  /** Clear once POST /auth/workspace has succeeded for this signup. */
  allocationDone: boolean;
  /** Workspace allocated on the backend (mirrors user.preferred_workspace). */
  allocatedWorkspace: OnboardingOutcome | null;
  /** True when the workspace was auto-assigned (skipped questionnaire). */
  autoAssigned: boolean;
  setAnswer: (questionId: string, optionId: string) => void;
  reset: () => void;
  /** Map answers (or a forced direct choice) to the primary workspace. */
  chooseWorkspace: (outcome: OnboardingOutcome, autoAssigned?: boolean) => OnboardingOutcome;
  /** Persist allocation to the backend; returns the final outcome or error. */
  commitAllocation: (
    outcome: OnboardingOutcome,
    opts?: { autoAssigned?: boolean },
  ) => Promise<{ ok: boolean; error?: string }>;
}

/** Recommend a workspace from questionnaire answers. */
export function recommendWorkspace(answers: Record<string, string>): OnboardingOutcome {
  if (answers.account_for === "business") return "business";
  if (answers.filing_frequency === "monthly") return "business";
  return "personal";
}

/** True when the current auth user's allocation is already recorded. */
export async function isAllocationComplete(): Promise<boolean> {
  try {
    const raw = localStorage.getItem("fbr-onboarding-v1");
    if (!raw) return false;
    const parsed = JSON.parse(raw) as {
      state?: { allocationDone?: boolean; allocatedWorkspace?: OnboardingOutcome | null };
    };
    const requested = new URLSearchParams(window.location.search).get("workspace");
    const flag = parsed?.state?.allocationDone === true;
    const ws = parsed?.state?.allocatedWorkspace;
    // If ?workspace= is present and differs (deep link), the user is allowed to
    // view that workspace even before finishing onboarding.
    if (requested === "business" || requested === "personal") {
      return flag || ws !== null;
    }
    return flag;
  } catch {
    return false;
  }
}

export const useOnboarding = create<OnboardingState>()(
  persist(
    (set, get) => ({
      answers: {},
      allocationDone: false,
      allocatedWorkspace: null,
      autoAssigned: false,

      setAnswer: (questionId, optionId) =>
        set((s) => ({ answers: { ...s.answers, [questionId]: optionId } })),

      reset: () =>
        set({ answers: {}, allocationDone: false, allocatedWorkspace: null, autoAssigned: false }),

      chooseWorkspace: (outcome, autoAssigned = false) => {
        set({ allocatedWorkspace: outcome, autoAssigned });
        // Drive the shell header switcher (shared store) to the outcome AND
        // gate it: doosri workspace ab nazar nahi aani chahiye.
        useWorkspace.getState().setAllowed(outcome);
        useWorkspace.getState().switchTo(outcome);
        // Keep the auth user mirror in sync (localStorage + RequireAuth).
        useAuth.getState().updateUser({ preferred_workspace: outcome });
        return outcome;
      },

      commitAllocation: async (outcome, opts) => {
        set({ allocatedWorkspace: outcome, autoAssigned: opts?.autoAssigned ?? false });

        const token = getStoredAuthToken();
        if (token) {
          try {
            await authApi.allocateWorkspace(outcome);
          } catch (err) {
            if (isUnauthorized(err)) {
              return { ok: false, error: "Session expired — please sign in again." };
            }
            const message = err instanceof Error ? err.message : "Allocation failed.";
            return { ok: false, error: message };
          }
        }
        // No backend session (dev/demo) — allocation recorded locally only.
        set({ allocationDone: true });
        get().chooseWorkspace(outcome, opts?.autoAssigned ?? false);
        return { ok: true };
      },
    }),
    {
      name: "fbr-onboarding-v1",
      partialize: (s) => ({
        allocationDone: s.allocationDone,
        allocatedWorkspace: s.allocatedWorkspace,
        autoAssigned: s.autoAssigned,
      }),
    },
  ),
);
