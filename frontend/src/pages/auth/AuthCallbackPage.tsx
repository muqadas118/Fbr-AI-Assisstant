import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSupabaseClient } from "@/lib/supabase";
import { Loading } from "@/components/shell/Loading";
import { StatusBanner } from "@/components/ui/StatusBanner";

export function AuthCallbackPage() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const client = getSupabaseClient();
    if (!client) {
      navigate("/personal/overview", { replace: true });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { error: exchangeError } = await client.auth.exchangeCodeForSession(
          window.location.href,
        );
        if (cancelled) return;
        if (exchangeError) {
          setError(exchangeError.message);
          return;
        }
        navigate("/personal/overview", { replace: true });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Sign-in callback failed.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (error) {
    return (
      <div className="auth-wrap" data-testid="auth-callback-error">
        <div className="auth-card">
        <div className="auth-crest" aria-hidden="true">FBR</div>
        <StatusBanner kind="err" title="Sign-in failed" description={error} testId="auth-callback-error-banner" />
        </div>
      </div>
    );
  }

  return (
    <div className="auth-wrap" data-testid="auth-callback">
      <div className="auth-card">
      <div className="auth-crest" aria-hidden="true">FBR</div>
      <Loading label="Completing sign-in…" testId="auth-callback-loading" />
      </div>
    </div>
  );
}
