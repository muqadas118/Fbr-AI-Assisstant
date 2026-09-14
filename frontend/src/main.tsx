import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { setAuthTokenGetter, setUnauthorizedHandler } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase";
import { useAuth } from "@/state/auth";
import "@/styles/tokens.css";
import "@/styles/app.css";
import "@/styles/gov-fbr.css";

// Wire Supabase JWT -> API Bearer header once at startup.
// getAccessToken() resolves to null when signed out / unconfigured,
// so unauthenticated flows (and tests) keep working.
setAuthTokenGetter(getAccessToken);
setUnauthorizedHandler(() => {
  const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (currentPath.startsWith("/login")) return;
  void useAuth.getState().signOut().finally(() => {
    window.location.replace(`/login?returnTo=${encodeURIComponent(currentPath)}`);
  });
});

// Restore session + subscribe to auth changes (supabase auto-persist).
void useAuth.getState().init();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
