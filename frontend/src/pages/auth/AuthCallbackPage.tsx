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
      <div className="app-main__inner" style={{ maxWidth: 480, margin: "0 auto", padding: "48px 20px" }} data-testid="auth-callback-error">
        <StatusBanner kind="err" title="Sign-in failed" description={error} testId="auth-callback-error-banner" />
      </div>
    );
  }

  return (
    <div className="app-main__inner" style={{ maxWidth: 480, margin: "0 auto", padding: "48px 20px" }} data-testid="auth-callback">
      <Loading label="Completing sign-in…" testId="auth-callback-loading" />
    </div>
  );
}
