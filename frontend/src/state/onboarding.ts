// ---------------------------------------------------------------------------
// Onboarding store — signup questionnaire + workspace allocation.
//
// Flow (modern SaaS style):
//   signup → a few professional qualifying questions → final step asks the
//   user to pick their workspace. Our recommendation (weighted score from
//   the answers) arrives pre-selected with a "Recommended" badge, but the
//   user's explicit click ALWAYS wins — recommend Business, user clicks
//   Personal → they get Personal.
//
// Allocation is persisted on the backend user row (preferred_workspace) via
// POST /auth/workspace so it survives reloads; the persisted local copy
// (fbr-onboarding-v1) only records completion for route gating.
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

/** Qualifying questions — asked before the workspace choice. */
export const ONBOARDING_QUESTIONS: Question[] = [
  {
    id: "profile",
    title: "Which best describes you?",
    options: [
      {
        id: "individual",
        label: "Individual or salaried professional",
        blurb: "Income tax return, salary tax, rent and investment withholding.",
      },
      {
        id: "freelancer",
        label: "Freelancer or consultant",
        blurb: "Freelance remittances, presumptive tax regimes, client invoicing.",
      },
      {
        id: "business",
        label: "Company, partnership or finance team",
        blurb: "Registered entities handling returns, statements and team filings.",
      },
    ],
  },
  {
    id: "primary_need",
    title: "What will you use the assistant for most?",
    options: [
      {
        id: "research",
        label: "Grounded tax research",
        blurb: "Cited answers from the Income Tax Ordinance, Sales Tax Act and SROs.",
      },
      {
        id: "filings",
        label: "Returns and filing deadlines",
        blurb: "Return readiness, compliance calendar and overdue alerts.",
      },
      {
        id: "calculations",
        label: "Tax calculations",
        blurb: "Salary, business, sales tax, withholding and penalty math.",
      },
      {
        id: "records",
        label: "Invoices and documents",
        blurb: "Invoice validation, ITC reconciliation, notice and document vault.",
      },
    ],
  },
  {
    id: "sales_tax",
    title: "Does your activity involve sales tax?",
    options: [
      {
        id: "registered",
        label: "Yes — I am sales-tax registered",
        blurb: "I file monthly or bi-monthly sales tax returns on the IRIS portal.",
      },
      {
        id: "occasional",
        label: "Occasionally, on purchases or assets",
        blurb: "Not registered, but sales tax appears in my expense records.",
      },
      {
        id: "none",
        label: "No — my exposure is income tax only",
        blurb: "I do not charge or file sales tax.",
      },
    ],
  },
  {
    id: "withholding",
    title: "Do you deduct or withhold tax for others?",
    options: [
      {
        id: "payroll",
        label: "Yes — salary, rent and contractor payments",
        blurb: "I run payroll or pay rent/services and deposit WHT statements.",
      },
      {
        id: "occasional",
        label: "Occasionally — bank profit, property deals",
        blurb: "Banks or buyers deduct at source; I claim it back in my return.",
      },
      {
        id: "none",
        label: "No — I have no deduction obligations",
        blurb: "Nothing to withhold or deposit on behalf of others.",
      },
    ],
  },
];

/** Weighted evidence toward the Business workspace. */
const SCORES: Record<string, Record<string, number>> = {
  profile: { individual: 0, freelancer: 1, business: 3 },
  primary_need: { research: 0, filings: 0, calculations: 0, records: 1 },
  sales_tax: { none: 0, occasional: 1, registered: 2 },
  withholding: { none: 0, occasional: 1, payroll: 2 },
};

/** Threshold on the weighted score for a Business recommendation. */
const BUSINESS_THRESHOLD = 3;

interface OnboardingState {
  /** Answers to the qualifying questions, keyed by question id (option id). */
  answers: Record<string, string>;
  /** Final-step selection by the user; overrides the recommendation. */
  explicitChoice: OnboardingOutcome | null;
  /** Clear once POST /auth/workspace has succeeded for this signup. */
  allocationDone: boolean;
  /** Workspace allocated on the backend (mirrors user.preferred_workspace). */
  allocatedWorkspace: OnboardingOutcome | null;
  /** True when the workspace was auto-assigned (skipped questionnaire). */
  autoAssigned: boolean;
  setAnswer: (questionId: string, optionId: string) => void;
  setExplicitChoice: (outcome: OnboardingOutcome) => void;
  reset: () => void;
  /** Map answers (or a forced direct choice) to the primary workspace. */
  chooseWorkspace: (outcome: OnboardingOutcome, autoAssigned?: boolean) => OnboardingOutcome;
  /** Persist allocation to the backend; returns the final outcome or error. */
  commitAllocation: (
    outcome: OnboardingOutcome,
    opts?: { autoAssigned?: boolean },
  ) => Promise<{ ok: boolean; error?: string }>;
}

/**
 * Evidence-based recommendation from the qualifying answers. This is only a
 * suggestion — the final step lets the user pick, and their pick wins.
 */
export function recommendWorkspace(answers: Record<string, string>): OnboardingOutcome {
  let score = 0;
  for (const [qid, weights] of Object.entries(SCORES)) {
    score += weights[answers[qid]] ?? 0;
  }
  return score >= BUSINESS_THRESHOLD ? "business" : "personal";
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
      explicitChoice: null,
      allocationDone: false,
      allocatedWorkspace: null,
      autoAssigned: false,

      setAnswer: (questionId, optionId) =>
        set((s) => ({ answers: { ...s.answers, [questionId]: optionId } })),

      setExplicitChoice: (outcome) => set({ explicitChoice: outcome }),

      reset: () =>
        set({
          answers: {},
          explicitChoice: null,
          allocationDone: false,
          allocatedWorkspace: null,
          autoAssigned: false,
        }),

      chooseWorkspace: (outcome, autoAssigned = false) => {
        set({ allocatedWorkspace: outcome, autoAssigned });
        // Drive the shell header switcher (shared store) to the outcome AND
        // gate it: the other workspace must stay hidden.
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
        // Answers survive a mid-questionnaire reload (cleared by reset() on
        // every fresh signup), so progress is never lost.
        answers: s.answers,
        explicitChoice: s.explicitChoice,
        allocationDone: s.allocationDone,
        allocatedWorkspace: s.allocatedWorkspace,
        autoAssigned: s.autoAssigned,
      }),
    },
  ),
);
