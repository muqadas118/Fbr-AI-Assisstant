// ---------------------------------------------------------------------------
// Supabase client — singleton for frontend auth wiring.
// Reads VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY via import.meta.env.
// Graceful fallback: null client + console.warn when not configured, so
// `npm run build` / `npm test` stay green without live credentials.
// Session persistence is handled by supabase-js (auto-persist +
// auto-refresh). Do NOT manually store raw JWTs in localStorage.
// ---------------------------------------------------------------------------

import {
  createClient,
  type AuthChangeEvent,
  type Session,
  type SupabaseClient,
} from "@supabase/supabase-js";

function readSupabaseUrl(): string {
  const value = (import.meta.env as unknown as Record<string, string | undefined>)[
    "VITE_SUPABASE_URL"
  ];
  return value && value.length > 0 ? value : "";
}

function readSupabaseAnonKey(): string {
  const value = (import.meta.env as unknown as Record<string, string | undefined>)[
    "VITE_SUPABASE_ANON_KEY"
  ];
  return value && value.length > 0 ? value : "";
}

export function isSupabaseConfigured(): boolean {
  return readSupabaseUrl().length > 0 && readSupabaseAnonKey().length > 0;
}

let cachedClient: SupabaseClient | null = null;
let warnedUnconfigured = false;

function warnUnconfiguredOnce(): void {
  if (!warnedUnconfigured) {
    warnedUnconfigured = true;
    console.warn(
      "[supabase] VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY not configured — auth disabled, API calls proceed without Bearer token.",
    );
  }
}

// Singleton accessor. Returns null when env is missing (graceful fallback).
export function getSupabaseClient(): SupabaseClient | null {
  if (!isSupabaseConfigured()) {
    warnUnconfiguredOnce();
    return null;
  }
  if (!cachedClient) {
    cachedClient = createClient(readSupabaseUrl(), readSupabaseAnonKey(), {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
      },
    });
  }
  return cachedClient;
}

// Eager singleton for convenient imports. Null when not configured.
export const supabase: SupabaseClient | null = getSupabaseClient();

// Resolve the current access token (JWT) or null when signed out / unconfigured.
export async function getAccessToken(): Promise<string | null> {
  const client = getSupabaseClient();
  if (!client) return null;
  try {
    const { data, error } = await client.auth.getSession();
    if (error) return null;
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

export type AuthStateCallback = (event: AuthChangeEvent, session: Session | null) => void;

// Thin wrapper so callers do not need a null-check on the client.
export function onAuthStateChange(callback: AuthStateCallback) {
  const client = getSupabaseClient();
  if (!client) {
    return { data: { subscription: { unsubscribe: () => undefined } } };
  }
  return client.auth.onAuthStateChange(callback);
}

export type { Session, SupabaseClient };
