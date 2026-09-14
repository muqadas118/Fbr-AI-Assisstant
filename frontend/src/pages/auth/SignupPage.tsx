import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/state/auth";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { StatusBanner } from "@/components/ui/StatusBanner";

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function SignupPage() {
  const navigate = useNavigate();
  const session = useAuth((s) => s.session);
  const signUp = useAuth((s) => s.signUp);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
    confirm?: string;
  }>({});

  if (session) {
    return <Navigate to="/personal/overview" replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: { email?: string; password?: string; confirm?: string } = {};
    if (!email.trim()) errs.email = "Email is required.";
    else if (!isValidEmail(email)) errs.email = "Enter a valid email address.";
    if (!password) errs.password = "Password is required.";
    else if (password.length < 6) errs.password = "Password must be at least 6 characters.";
    if (confirm !== password) errs.confirm = "Passwords do not match.";
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setSubmitting(true);
    setError(null);
    setNotice(null);
    const { error: authError } = await signUp(email, password);
    setSubmitting(false);
    if (authError) {
      setError(authError);
      return;
    }
    // Supabase may require email confirmation (no session yet) or auto-sign-in.
    const currentSession = useAuth.getState().session;
    if (currentSession) {
      navigate("/personal/overview", { replace: true });
    } else {
      setNotice("Account created. Check your email to confirm, then sign in.");
    }
  };

  return (
    <div
      className="app-main__inner"
      style={{ maxWidth: 480, margin: "0 auto", padding: "48px 20px" }}
      data-testid="signup-page"
    >
      <p className="page-eyebrow">FBR AI Tax &amp; Compliance</p>
      <h1 className="page-title">Create account</h1>
      <p className="page-lede">Create an account to access your personal and business workspaces.</p>

      {error ? (
        <StatusBanner kind="err" title="Sign-up failed" description={error} testId="signup-error" />
      ) : null}
      {notice ? (
        <StatusBanner kind="ok" title="Check your email" description={notice} testId="signup-notice" />
      ) : null}

      <Card title="New account" subtitle="Use a valid email address and a password of 6+ characters.">
        <form onSubmit={handleSubmit} noValidate data-testid="signup-form">
          <Field label="Email *" error={fieldErrors.email}>
            <input
              type="email"
              className="field__input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              data-testid="signup-email-input"
              aria-required="true"
            />
          </Field>
          <Field label="Password *" error={fieldErrors.password}>
            <input
              type="password"
              className="field__input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 6 characters"
              autoComplete="new-password"
              data-testid="signup-password-input"
              aria-required="true"
            />
          </Field>
          <Field label="Confirm password *" error={fieldErrors.confirm}>
            <input
              type="password"
              className="field__input"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat password"
              autoComplete="new-password"
              data-testid="signup-confirm-input"
              aria-required="true"
            />
          </Field>
          <div className="form__actions">
            <Button
              type="submit"
              variant="primary"
              loading={submitting}
              disabled={submitting}
              data-testid="signup-submit"
            >
              {submitting ? "Creating…" : "Create account"}
            </Button>
            <span className="card__body-text">
              Have an account? <Link to="/login">Sign in</Link>
            </span>
          </div>
        </form>
      </Card>
    </div>
  );
}
