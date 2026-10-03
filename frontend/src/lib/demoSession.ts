/**
 * Stable per-browser demo identity for signed-out sessions (dev without
 * Supabase keys). The same id is reused across Inbox / Subordinates /
 * Workspaces so backend data (monitor subscription, teams, workspaces)
 * attaches consistently to one identity per browser.
 */

const DEMO_USER_KEY = "fbr_demo_user_id";

export function getDemoUserId(): string {
  try {
    const existing = localStorage.getItem(DEMO_USER_KEY);
    if (existing) return existing;
    const raw =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `demo-${Date.now()}`;
    const id = `demo-${raw.slice(0, 8)}`;
    localStorage.setItem(DEMO_USER_KEY, id);
    return id;
  } catch {
    return "demo-user";
  }
}
