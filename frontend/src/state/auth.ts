// ---------------------------------------------------------------------------
// Auth store — Zustand wrapper around the FBR backend's own auth system
// (POST /auth/signup, /auth/login, /auth/logout; opaque bearer session
// tokens persisted in localStorage). No external provider required.
//
// The tokens are opaque strings issued by the backend's own session
// registry (NOT third-party JWTs), so localStorage is the intended
// durable store — the session survives browser restarts, matching the
// backend's long-lived session contract.
// ---------------------------------------------------------------------------

import { create } from "zustand";
import { ApiError, authApi, isUnauthorized } from "@/lib/api";
import { useWorkspace, type WorkspaceId } from "@/state/workspace";

export interface BackendUser {
  id: string;
  email: string;
  name: string;
  role: string;
  organization?: string | null;
  /** Workspace allocated by the signup onboarding (POST /auth/workspace). */
  preferred_workspace?: string | null;
  created_at?: string;
}

export interface AuthResult {
  error: string | null;
}

interface AuthState {
  user: BackendUser | null;
  token: string | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (email: string, password: string, name?: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
  init: () => Promise<() => void>;
  /** Merge fields into the current user (and localStorage mirror). */
  updateUser: (patch: Partial<BackendUser>) => void;
}

const TOKEN_KEY = "fbr_auth_token";
const USER_KEY = "fbr_auth_user";

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function readStoredUser(): BackendUser | null {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BackendUser;
    return parsed && typeof parsed.email === "string" ? parsed : null;
  } catch {
    return null;
  }
}

function persistSession(token: string, user: BackendUser): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // Private mode / storage full — session lives for the tab only.
  }
}

function clearStoredSession(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    // ignore
  }
}

export function getStoredAuthToken(): string | null {
  return readStoredToken();
}

function friendlyAuthError(message: string): string {
  if (/already exists/i.test(message)) {
    return "An account with this email already exists. Try signing in.";
  }
  if (/invalid email or password/i.test(message)) {
    return "Invalid email or password.";
  }
  if (/email not confirmed/i.test(message)) {
    return "Please confirm your email before signing in.";
  }
  return message;
}

/**
 * Apply the account's allocated workspace to the shell gating right after a
 * credential flow (login/signup). Without this the switcher showed BOTH
 * workspaces after login — the allocation was only read at app boot or
 * during onboarding. null resets gating for pre-onboarding accounts.
 */
function applyWorkspaceGate(preferred: string | null | undefined): void {
  useWorkspace.getState().setAllowed(
    preferred === "personal" || preferred === "business"
      ? (preferred as WorkspaceId)
      : null,
  );
}

export const useAuth = create<AuthState>((set) => ({
  user: readStoredUser(),
  token: readStoredToken(),
  loading: false,
  initialized: true,
  error: null,

  signIn: async (email, password) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.login(email.trim(), password);
      persistSession(res.token, res.user as BackendUser);
      set({ user: res.user as BackendUser, token: res.token, loading: false, error: null });
      applyWorkspaceGate((res.user as BackendUser).preferred_workspace);
      return { error: null };
    } catch (err) {
      const message =
        err instanceof ApiError
          ? friendlyAuthError(err.detail)
          : err instanceof Error
            ? err.message
            : "Sign-in failed.";
      set({ loading: false, error: message });
      return { error: message };
    }
  },

  signUp: async (email, password, name) => {
    set({ loading: true, error: null });
    try {
      const res = await authApi.signup(email.trim(), password, name);
      persistSession(res.token, res.user as BackendUser);
      set({ user: res.user as BackendUser, token: res.token, loading: false, error: null });
      return { error: null };
    } catch (err) {
      const message =
        err instanceof ApiError
          ? friendlyAuthError(err.detail)
          : err instanceof Error
            ? err.message
            : "Sign-up failed.";
      set({ loading: false, error: message });
      return { error: message };
    }
  },

  signOut: async () => {
    const token = readStoredToken();
    clearStoredSession();
    set({ user: null, token: null, loading: false, error: null });
    // Reset workspace gating so the next login starts clean.
    applyWorkspaceGate(null);
    if (token) {
      try {
        await authApi.logout(token);
      } catch {
        // Non-fatal: local session is already cleared.
      }
    }
  },

  updateUser: (patch) => {
    set((s) => {
      if (!s.user) return s;
      const merged = { ...s.user, ...patch } as BackendUser;
      try {
        window.localStorage.setItem(USER_KEY, JSON.stringify(merged));
      } catch {
        // Non-fatal: state still updated for this session.
      }
      return { user: merged };
    });
  },

  init: async () => {
    // Restore + validate any persisted session. A 401 (expired/revoked
    // token) drops the session; any other failure (network blip, 5xx)
    // KEEPS it — a transient error must never log out a valid user.
    const token = readStoredToken();
    if (!token) {
      set({ user: null, token: null, loading: false, initialized: true });
      return () => undefined;
    }
    try {
      const res = await authApi.me(token);
      const user = (res.user ?? res) as BackendUser;
      persistSession(token, user);
      set({ user, token, loading: false, initialized: true });
    } catch (err) {
      if (isUnauthorized(err)) {
        // Backend rejected the session — the stored copy is worthless.
        clearStoredSession();
        set({ user: null, token: null, loading: false, initialized: true });
      } else {
        // Could not reach the server — keep the stored session and surface
        // a connection error; the next authenticated request retries.
        set({
          user: readStoredUser(),
          token,
          loading: false,
          initialized: true,
          error:
            "Could not reach the server to restore your session. Your session is kept — check your connection.",
        });
      }
    }
    return () => undefined;
  },
}));
