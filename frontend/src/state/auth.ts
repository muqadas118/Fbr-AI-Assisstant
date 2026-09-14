// ---------------------------------------------------------------------------
// Auth store — Zustand wrapper around the Supabase singleton.
// Session persistence is handled by supabase-js (auto-persist +
// auto-refresh). Do NOT manually store raw JWT strings in localStorage.
// ---------------------------------------------------------------------------

import { create } from "zustand";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseClient } from "@/lib/supabase";

export interface AuthResult {
  error: string | null;
}

interface AuthState {
  user: User | null;
  session: Session | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (email: string, password: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
  init: () => Promise<() => void>;
}

function friendlyAuthError(message: string): string {
  if (/invalid login credentials/i.test(message)) {
    return "Invalid email or password.";
  }
  if (/user already registered/i.test(message)) {
    return "An account with this email already exists. Try signing in.";
  }
  if (/email not confirmed/i.test(message)) {
    return "Please confirm your email before signing in.";
  }
  return message;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  session: null,
  loading: true,
  initialized: false,
  error: null,

  init: async () => {
    const client = getSupabaseClient();
    if (!client) {
      set({ user: null, session: null, loading: false, initialized: true });
      return () => undefined;
    }
    set({ loading: true, error: null });
    try {
      const { data } = await client.auth.getSession();
      set({
        user: data.session?.user ?? null,
        session: data.session,
        loading: false,
        initialized: true,
      });
    } catch (err) {
      set({
        user: null,
        session: null,
        loading: false,
        initialized: true,
        error: err instanceof Error ? err.message : "Failed to restore session.",
      });
    }
    const { data: listener } = client.auth.onAuthStateChange((_event, session) => {
      set({
        user: session?.user ?? null,
        session,
        loading: false,
        initialized: true,
      });
    });
    return () => {
      listener.subscription.unsubscribe();
    };
  },

  signIn: async (email, password) => {
    const client = getSupabaseClient();
    if (!client) {
      return {
        error:
          "Auth is not configured (missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY).",
      };
    }
    set({ loading: true, error: null });
    try {
      const { data, error } = await client.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) {
        const friendly = friendlyAuthError(error.message);
        set({ loading: false, error: friendly });
        return { error: friendly };
      }
      set({
        user: data.user,
        session: data.session,
        loading: false,
        error: null,
      });
      return { error: null };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sign-in failed.";
      set({ loading: false, error: message });
      return { error: message };
    }
  },

  signUp: async (email, password) => {
    const client = getSupabaseClient();
    if (!client) {
      return {
        error:
          "Auth is not configured (missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY).",
      };
    }
    set({ loading: true, error: null });
    try {
      const { data, error } = await client.auth.signUp({
        email: email.trim(),
        password,
      });
      if (error) {
        const friendly = friendlyAuthError(error.message);
        set({ loading: false, error: friendly });
        return { error: friendly };
      }
      set({
        user: data.user,
        session: data.session,
        loading: false,
        error: null,
      });
      return { error: null };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Sign-up failed.";
      set({ loading: false, error: message });
      return { error: message };
    }
  },

  signOut: async () => {
    const client = getSupabaseClient();
    if (client) {
      try {
        await client.auth.signOut();
      } catch {
        // Non-fatal: still clear local auth state below.
      }
    }
    set({ user: null, session: null, loading: false, error: null });
  },
}));
