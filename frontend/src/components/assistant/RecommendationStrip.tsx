import { useMemo, useState } from "react";
import clsx from "clsx";
import { useNavigate } from "react-router-dom";
import { api, type Recommendation } from "@/lib/api";
import { useNotification } from "@/state/notifications";

/**
 * Recommendations derived from the user's own question history, rendered
 * under an assistant answer. Empty list renders nothing at call sites.
 */

const KIND_META: Record<string, { icon: string; label: string }> = {
  // Kinds emitted by app/learning/recommender.py
  deadline: { icon: "⏰", label: "Deadline" },
  calculator: { icon: "🧮", label: "Calculator" },
  notice_followup: { icon: "⚠️", label: "Notice" },
  document_followup: { icon: "📄", label: "Document" },
  learning_topic: { icon: "💡", label: "Topic" },
  verification: { icon: "🔎", label: "Verification" },
  tax_health: { icon: "📈", label: "Tax health" },
  // Legacy / other kinds still rendered if they ever appear
  filing: { icon: "📅", label: "Filing" },
  document: { icon: "📄", label: "Document" },
  payment: { icon: "💳", label: "Payment" },
  registration: { icon: "🧾", label: "Registration" },
  notice: { icon: "⚠️", label: "Notice" },
  tip: { icon: "💡", label: "Tip" },
  action: { icon: "✅", label: "Action" },
  insight: { icon: "📈", label: "Insight" },
};

function kindMeta(kind: string): { icon: string; label: string } {
  const known = KIND_META[kind];
  if (known) return known;
  const label = kind.replace(/[_-]+/g, " ").trim();
  return { icon: "⭐", label: label || "Suggestion" };
}

/**
 * The backend `priority` is a number (higher = shown first). Turn it into a
 * short band label for the badge instead of rendering the raw integer.
 */
function priorityLabel(priority: number): "high" | "medium" | "low" {
  if (priority >= 85) return "high";
  if (priority >= 53) return "medium";
  return "low";
}

export function RecommendationStrip({
  recommendations,
  testId,
}: {
  recommendations: Recommendation[];
  testId?: string;
}) {
  const navigate = useNavigate();
  const { show: notify } = useNotification();
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  const visible = useMemo(
    () => recommendations.filter((r) => !dismissed.includes(r.id)),
    [recommendations, dismissed],
  );

  if (visible.length === 0) return null;

  const dismiss = async (rec: Recommendation) => {
    setBusyId(rec.id);
    // Optimistic: hide immediately, restore only if the server refuses.
    setDismissed((d) => [...d, rec.id]);
    try {
      await api.personalization.dismissRecommendation(rec.id);
      notify("ok", "Recommendation dismissed.");
    } catch {
      setDismissed((d) => d.filter((id) => id !== rec.id));
      notify("err", "Could not dismiss that recommendation — please try again.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="recs" data-testid={testId}>
      <div className="recs__head">
        <span className="recs__title">For you</span>
        <span className="recs__hint">Based on your own questions</span>
      </div>
      <ul className="recs__list">
        {visible.map((rec) => {
          const meta = kindMeta(rec.kind);
          const busy = busyId === rec.id;
          return (
            <li className="recs__item" key={rec.id} data-testid={testId ? `${testId}-item` : undefined}>
              <span className="recs__icon" aria-hidden>
                {meta.icon}
              </span>
              <div className="recs__body">
                <div className="recs__meta">
                  <span className="recs__kind">{meta.label}</span>
                  {rec.priority ? (
                    <span
                      className={clsx("recs__priority", `recs__priority--${priorityLabel(rec.priority)}`)}
                    >
                      {priorityLabel(rec.priority)}
                    </span>
                  ) : null}
                </div>
                <p className="recs__item-title">{rec.title}</p>
                {rec.body ? <p className="recs__text">{rec.body}</p> : null}
                <div className="recs__actions">
                  {rec.action_path ? (
                    <button
                      type="button"
                      className="recs__action"
                      onClick={() => navigate(rec.action_path)}
                      data-testid={testId ? `${testId}-action` : undefined}
                    >
                      {rec.action_label || "Open"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="recs__dismiss"
                    onClick={() => void dismiss(rec)}
                    disabled={busy}
                    aria-label={`Dismiss: ${rec.title}`}
                    data-testid={testId ? `${testId}-dismiss` : undefined}
                  >
                    {busy ? "…" : "Dismiss"}
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
