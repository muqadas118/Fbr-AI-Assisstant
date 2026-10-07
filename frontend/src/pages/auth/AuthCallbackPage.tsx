import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loading } from "@/components/shell/Loading";

/**
 * Legacy OAuth/email-confirmation callback. First-party backend auth no
 * longer uses redirect callbacks — sessions are issued directly on
 * signup/login — so any landing here goes straight into the app.
 */
export function AuthCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      navigate("/personal/overview", { replace: true });
    }, 400);
    return () => window.clearTimeout(timer);
  }, [navigate]);

  return (
    <div className="auth-wrap" data-testid="auth-callback">
      <div className="auth-card">
        <div className="auth-crest" aria-hidden="true">FBR</div>
        <Loading label="Completing sign-in…" testId="auth-callback-loading" />
      </div>
    </div>
  );
}
