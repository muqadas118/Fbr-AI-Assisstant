import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/state/auth";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { StatusBanner } from "@/components/ui/StatusBanner";

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useAuth((s) => s.session);
  const signIn = useAuth((s) => s.signIn);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  if (session) {
    return <Navigate to="/personal/overview" replace />;
  }

  const from =
    (location.state as { from?: string } | null)?.from ?? "/personal/overview";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: { email?: string; password?: string } = {};
    if (!email.trim()) errs.email = "Email is required.";
    else if (!isValidEmail(email)) errs.email = "Enter a valid email address.";
    if (!password) errs.password = "Password is required.";
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setSubmitting(true);
    setError(null);
    const { error: authError } = await signIn(email, password);
    setSubmitting(false);
    if (authError) {
      setError(authError);
      return;
    }
    navigate(from, { replace: true });
  };

  return (
    <div className="auth-wrap" data-testid="login-page">
      <div className="auth-card">
      <div className="auth-crest" aria-hidden="true">FBR</div>
      <p className="page-eyebrow">FBR AI Tax &amp; Compliance</p>
      <h1 className="page-title">Sign in</h1>
      <p className="page-lede">Sign in to access your personal and business workspaces.</p>

      {error ? (
        <StatusBanner kind="err" title="Sign-in failed" description={error} testId="login-error" />
      ) : null}

      <Card title="Welcome back" subtitle="Use your account email and password.">
        <form onSubmit={handleSubmit} noValidate data-testid="login-form">
          <Field label="Email *" error={fieldErrors.email}>
            <input
              type="email"
              className="field__input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              data-testid="login-email-input"
              aria-required="true"
            />
          </Field>
          <Field label="Password *" error={fieldErrors.password}>
            <input
              type="password"
              className="field__input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password"
              autoComplete="current-password"
              data-testid="login-password-input"
              aria-required="true"
            />
          </Field>
          <div className="form__actions">
            <Button
              type="submit"
              variant="primary"
              loading={submitting}
              disabled={submitting}
              data-testid="login-submit"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
            <span className="card__body-text">
              No account? <Link to="/signup">Create one</Link>
            </span>
          </div>
        </form>
      </Card>
      </div>
    </div>
  );
}
