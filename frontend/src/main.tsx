import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { setAuthTokenGetter, setUnauthorizedHandler } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase";
import { useAuth } from "@/state/auth";
import "@/styles/tokens.css";
import "@/styles/app.css";
import "@/styles/inbox.css";
import "@/styles/team.css";
import "@/styles/sections.css";
import "@/styles/workspaces.css";
import "@/styles/readiness.css";
import "@/styles/gov-fbr.css";

// Wire Supabase JWT -> API Bearer header once at startup.
// getAccessToken() resolves to null when signed out / unconfigured,
// so unauthenticated flows (and tests) keep working.
setAuthTokenGetter(getAccessToken);
setUnauthorizedHandler(() => {
  // Session rejected/expired (401 from API) → send user to login.
  // main.tsx lives outside <BrowserRouter>, so use a full navigation.
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
});

// Restore session + subscribe to auth changes (supabase auto-persist).
void useAuth.getState().init();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
