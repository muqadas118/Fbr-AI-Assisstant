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

const WORKSPACE_CHOICES: Record<
  OnboardingOutcome,
  { label: string; blurb: string; features: string[] }
> = {
  personal: {
    label: "Personal Workspace",
    blurb: "For individuals, salaried professionals and freelancers.",
    features: [
      "Salary and income tax calculator",
      "Annual return readiness and deadlines",
      "Notices, appeals and AI tax answers",
    ],
  },
  business: {
    label: "Business Workspace",
    blurb: "For registered entities, finance and accounting teams.",
    features: [
      "Sales tax, WHT statements and ITC reconcile",
      "Invoice intelligence and compliance reports",
      "Team roles, FBR monitor and audit trail",
    ],
  },
};

export function OnboardingFlow() {
  const navigate = useNavigate();
  const answers = useOnboarding((s) => s.answers);
  const setAnswer = useOnboarding((s) => s.setAnswer);
  const explicitChoice = useOnboarding((s) => s.explicitChoice);
  const setExplicitChoice = useOnboarding((s) => s.setExplicitChoice);
  const commitAllocation = useOnboarding((s) => s.commitAllocation);

  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const questions = ONBOARDING_QUESTIONS;
  const totalSteps = questions.length + 1; // + workspace selection step
  const onWorkspaceStep = step >= questions.length;
  const contentAnswered = questions.every((q) => answers[q.id]);

  // Evidence-based recommendation from the answers so far.
  const recommendation = useMemo<OnboardingOutcome>(
    () => recommendWorkspace(answers),
    [answers],
  );
  // The user's explicit click always beats the recommendation.
  const selected = recommendedOrChosen(recommendation, explicitChoice);

  const handleFinish = async () => {
    setSubmitting(true);
    setError(null);
    const res = await commitAllocation(selected);
    setSubmitting(false);
    if (!res.ok) {
      setError(res.error ?? "We could not set up your workspace — please try again.");
      return;
    }
    navigate(selected === "business" ? "/business/overview" : "/personal/overview", {
      replace: true,
    });
  };

  const question = questions[Math.min(step, questions.length - 1)];
  const chosen = answers[question.id];

  return (
    <div className="auth-wrap onboarding" data-testid="onboarding-page">
      <div className="auth-card onboarding__card">
        <div className="auth-crest" aria-hidden="true">FBR</div>
        <p className="page-eyebrow">Account setup</p>
        <h1 className="page-title">Set up your workspace</h1>
        <p className="page-lede">
          A few quick questions so we configure the right tools for how you work
          with the FBR. You stay in control — the last step is your choice.
        </p>

        <ol className="onboarding__progress" aria-label="Setup progress">
          {Array.from({ length: totalSteps }, (_, i) => (
            <li
              key={i}
              className={clsx(
                "onboarding__dot",
                i < step && "onboarding__dot--done",
                i === step && "onboarding__dot--active",
              )}
              aria-current={i === step ? "step" : undefined}
            />
          ))}
        </ol>

        {!onWorkspaceStep ? (
          <Card
            title={`Question ${step + 1} of ${totalSteps} · ${question.title}`}
            testId="onboarding-question"
          >
            <div className="onboarding__options" role="radiogroup" aria-label={question.title}>
              {question.options.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  role="radio"
                  aria-checked={chosen === opt.id}
                  className={clsx(
                    "onboarding__opt",
                    chosen === opt.id && "onboarding__opt--active",
                  )}
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
              <Button
                variant="primary"
                disabled={!chosen}
                onClick={() => setStep((s) => s + 1)}
                data-testid="onboarding-next"
              >
                Next
              </Button>
            </div>

            {/* Live preview of where the answers are pointing. */}
            {contentAnswered ? (
              <div
                className={clsx("onboarding__summary", `onboarding__summary--${recommendation}`)}
                data-testid="onboarding-summary"
              >
                <span className="onboarding__summary-label">Based on your answers</span>
                <strong>We suggest the {WORKSPACE_CHOICES[recommendation].label}</strong>
                <small>You will confirm this on the last step.</small>
              </div>
            ) : null}
          </Card>
        ) : (
          <Card
            title={`Question ${totalSteps} of ${totalSteps} · Choose your workspace`}
            testId="onboarding-workspace-choice"
          >
            <div className="onboarding__workspaces" role="radiogroup" aria-label="Workspace choice">
              {(Object.keys(WORKSPACE_CHOICES) as OnboardingOutcome[]).map((ws) => {
                const info = WORKSPACE_CHOICES[ws];
                const active = selected === ws;
                const recommended = recommendation === ws;
                return (
                  <button
                    key={ws}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    className={clsx("workspace-card", active && "workspace-card--active")}
                    onClick={() => setExplicitChoice(ws)}
                    data-testid={`workspace-choice-${ws}`}
                  >
                    {recommended ? (
                      <span className="workspace-card__badge" data-testid={`workspace-badge-${ws}`}>
                        ★ Recommended
                      </span>
                    ) : null}
                    <span className="workspace-card__check" aria-hidden>
                      {active ? "✓" : ""}
                    </span>
                    <strong>{info.label}</strong>
                    <small className="workspace-card__blurb">{info.blurb}</small>
                    <ul className="workspace-card__features">
                      {info.features.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  </button>
                );
              })}
            </div>

            {explicitChoice !== null && explicitChoice !== recommendation ? (
              <p className="onboarding__override-note" data-testid="onboarding-override-note">
                Our suggestion was the {WORKSPACE_CHOICES[recommendation].label}, but your own
                selection always decides.
              </p>
            ) : null}

            <div className="form__actions onboarding__actions">
              <Button
                variant="ghost"
                size="sm"
                disabled={submitting}
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                data-testid="onboarding-back"
              >
                Back
              </Button>
              <Button
                variant="primary"
                loading={submitting}
                onClick={handleFinish}
                data-testid="onboarding-finish"
              >
                {submitting
                  ? "Setting up…"
                  : `Enter ${selected === "business" ? "Business" : "Personal"} Workspace`}
              </Button>
            </div>
          </Card>
        )}

        {error ? (
          <StatusBanner kind="err" title="Setup failed" description={error} testId="onboarding-error" />
        ) : null}
      </div>
    </div>
  );
}

/** Explicit user click wins over the evidence-based recommendation. */
function recommendedOrChosen(
  recommendation: OnboardingOutcome,
  explicit: OnboardingOutcome | null,
): OnboardingOutcome {
  return explicit ?? recommendation;
}
