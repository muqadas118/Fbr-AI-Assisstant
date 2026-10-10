// ---------------------------------------------------------------------------
// Supabase client — REMOVED (dead code).
//
// The previous Supabase layer (getSupabaseClient / getAccessToken /
// onAuthStateChange / the `supabase` singleton) had ZERO importers: nothing
// in src/ ever called into it, and the API client's Bearer wiring was in
// fact pointed at the backend's own token getter, not at Supabase — see
// `setAuthTokenGetter(async () => getStoredAuthToken())` in main.tsx.
//
// The app authenticates against the FBR backend's first-party auth system
// (POST /auth/signup | /auth/login | /auth/logout | /auth/me) with opaque
// session tokens; no external auth provider is involved. That made this
// whole module dead weight, so its code was removed.
//
// This file is intentionally kept as a documented placeholder (nothing
// imports it). @supabase/supabase-js has been removed from package.json
// because zero importers remain; any future Supabase integration must
// re-add that dependency first. Note: package-lock.json still carries it
// in the root dependency block until the lockfile is regenerated with
// `npm install`, so regeneration is part of any future re-add.
// ---------------------------------------------------------------------------

export {};
