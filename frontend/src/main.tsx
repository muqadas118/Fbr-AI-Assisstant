import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { setAuthTokenGetter } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase";
import { useAuth } from "@/state/auth";
import "@/styles/tokens.css";
import "@/styles/app.css";

// Wire Supabase JWT -> API Bearer header once at startup.
// getAccessToken() resolves to null when signed out / unconfigured,
// so unauthenticated flows (and tests) keep working.
setAuthTokenGetter(getAccessToken);

// Restore session + subscribe to auth changes (supabase auto-persist).
void useAuth.getState().init();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
