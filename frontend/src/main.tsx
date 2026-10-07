import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { setAuthTokenGetter, setUnauthorizedHandler } from "@/lib/api";
import { getStoredAuthToken } from "@/state/auth";
import { useAuth } from "@/state/auth";
import { useOnboarding } from "@/state/onboarding";
import { useWorkspace } from "@/state/workspace";
import "@/styles/tokens.css";
import "@/styles/app.css";
import "@/styles/inbox.css";
import "@/styles/team.css";
import "@/styles/sections.css";
import "@/styles/workspaces.css";
import "@/styles/readiness.css";
import "@/styles/gov-fbr.css";

// Wire the backend session token -> API Bearer header once at startup.
// getStoredAuthToken() resolves to null when signed out, so
// unauthenticated flows (and tests) keep working.
setAuthTokenGetter(async () => getStoredAuthToken());
setUnauthorizedHandler(() => {
  // Session rejected/expired (401 from API) → send user to login.
  // main.tsx lives outside <BrowserRouter>, so use a full navigation.
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
});

// Restore + validate the persisted session (drops it on 401).
void useAuth.getState().init().then(() => {
  // Workspace gating: backend user row par allocated workspace ko shell
  // mein allow karo. Login users (purane accounts, allocation ke bina)
  // ko dono workspaces milte hain — jaisa pehle tha.
  const user = useAuth.getState().user as { preferred_workspace?: string | null } | null;
  const ws = user?.preferred_workspace;
  if (ws === "personal" || ws === "business") {
    useWorkspace.getState().setAllowed(ws);
    void useOnboarding.getState().chooseWorkspace(ws, true);
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
