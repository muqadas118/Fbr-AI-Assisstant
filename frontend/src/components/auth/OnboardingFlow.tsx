import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import {
  ONBOARDING_QUESTIONS,
  recommendWorkspace,
  useOnboarding,
  type OnboardingOutcome,
} from "@/state/onboarding";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";

const OUTCOME_COPY: Record<OnboardingOutcome, { label: string; blurb: string }> = {
  personal: {
    label: "Personal Workspace",
    blurb: "Salary tax, personal returns, notices — sab kuch ek jagah.",
  },
  business: {
    label: "Business Workspace",
    blurb: "Sales tax, withholding, team, monitor — company-grade tooling.",
  },
};

export function OnboardingFlow() {
  const navigate = useNavigate();
  const answers = useOnboarding((s) => s.answers);
  const setAnswer = useOnboarding((s) => s.setAnswer);
  const commitAllocation = useOnboarding((s) => s.commitAllocation);

  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const questions = ONBOARDING_QUESTIONS;
  const last = step >= questions.length - 1;
  const allAnswered = questions.every((q) => answers[q.id]);
  const outcome = useMemo<OnboardingOutcome>(() => recommendWorkspace(answers), [answers]);

  const handleFinish = async () => {
    setSubmitting(true);
    setError(null);
    const res = await commitAllocation(outcome);
    setSubmitting(false);
    if (!res.ok) {
      setError(res.error ?? "Workspace allocate nahi ho saka — dobara koshish karein.");
      return;
    }
    navigate(outcome === "business" ? "/business/overview" : "/personal/overview", { replace: true });
  };

  const question = questions[step];
  const chosen = answers[question.id];

  return (
    <div className="auth-wrap onboarding" data-testid="onboarding-page">
      <div className="auth-card onboarding__card">
        <div className="auth-crest" aria-hidden="true">FBR</div>
        <p className="page-eyebrow">Account setup</p>
        <h1 className="page-title">Aap ka workspace tay karein</h1>
        <p className="page-lede">
          Chand sawal — hum aap ki profile ke mutabiq sahi workspace allocate kar denge.
        </p>

        <ol className="onboarding__progress" aria-label="Setup progress">
          {questions.map((q, i) => (
            <li
              key={q.id}
              className={clsx(
                "onboarding__dot",
                i < step && "onboarding__dot--done",
                i === step && "onboarding__dot--active",
              )}
              aria-current={i === step ? "step" : undefined}
            />
          ))}
        </ol>

        <Card title={`${step + 1}/${questions.length} · ${question.title}`} testId="onboarding-question">
          <div className="onboarding__options" role="radiogroup" aria-label={question.title}>
            {question.options.map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={chosen === opt.id}
                className={clsx("onboarding__opt", chosen === opt.id && "onboarding__opt--active")}
                onClick={() => setAnswer(question.id, opt.id)}
                data-testid={`onboarding-opt-${opt.id}`}
              >
                <span className="onboarding__opt-check" aria-hidden>
                  {chosen === opt.id ? "✓" : ""}
                </span>
                <span className="onboarding__opt-body">
                  <strong>{opt.label}</strong>
                  <small>{opt.blurb}</small>
                </span>
              </button>
            ))}
          </div>

          <div className="form__actions onboarding__actions">
            <Button
              variant="ghost"
              size="sm"
              disabled={step === 0 || submitting}
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              data-testid="onboarding-back"
            >
              Back
            </Button>
            {last ? (
              <Button
                variant="primary"
                loading={submitting}
                disabled={!allAnswered || submitting}
                onClick={handleFinish}
                data-testid="onboarding-finish"
              >
                {submitting ? "Setting up…" : "Workspace allocate karein"}
              </Button>
            ) : (
              <Button
                variant="primary"
                disabled={!chosen}
                onClick={() => setStep((s) => s + 1)}
                data-testid="onboarding-next"
              >
                Next
              </Button>
            )}
          </div>
        </Card>

        {/* Recommended workspace preview — answers change this live. */}
        <div className={clsx("onboarding__summary", `onboarding__summary--${outcome}`)} data-testid="onboarding-summary">
          <span className="onboarding__summary-label">Recommended for you</span>
          <strong>{OUTCOME_COPY[outcome].label}</strong>
          <small>{OUTCOME_COPY[outcome].blurb}</small>
        </div>

        {error ? (
          <StatusBanner kind="err" title="Setup failed" description={error} testId="onboarding-error" />
        ) : null}
      </div>
    </div>
  );
}
