import { useCallback, useEffect, useState } from "react";
import { api, type PersonalizationProfile } from "@/lib/api";
import { useNotification } from "@/state/notifications";
import { Field } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { StatusBanner } from "@/components/ui/StatusBanner";

/**
 * "For you" panel — the self-learning surface of the assistant.
 * Shows what the assistant learned from this account's questions, lets the
 * user switch learning on/off, and deletes every learned signal on request.
 * Every action carries loading + error state and a toast; a failing
 * personalization endpoint never breaks the surrounding chat.
 */

export interface PersonalizationPanelProps {
  open: boolean;
  onClose: () => void;
  testId?: string;
}

const HONEST_NOTE =
  "Learning is on-device-per-account: your questions shape your recommendations. We never use your data to train shared models.";

/** entity_type / tax_year live inside the opaque signals bag. */
function signalText(signals: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = signals[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return null;
}

function formatLastActive(value: string | null): string {
  if (!value) return "No activity recorded yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No activity recorded yet";
  return `Last active ${date.toLocaleString()}`;
}

export function PersonalizationPanel({ open, onClose, testId }: PersonalizationPanelProps) {
  const { show: notify } = useNotification();
  const [profile, setProfile] = useState<PersonalizationProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const fresh = await api.personalization.getProfile();
      setProfile(fresh);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not load your personalization profile.";
      setError(message);
      notify("err", "Could not load your personalization profile.");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!open) return null;

  const enabled = profile?.enabled ?? false;
  const topDomains = profile?.top_domains ?? [];
  const entityType = profile ? signalText(profile.signals, ["entity_type", "entityType"]) : null;
  const taxYear = profile ? signalText(profile.signals, ["tax_year", "taxYear"]) : null;

  const onToggle = async (next: boolean) => {
    setToggling(true);
    try {
      const res = await api.personalization.setPersonalization(next);
      setProfile((prev) => (prev ? { ...prev, enabled: res.enabled } : prev));
      notify(
        "ok",
        next
          ? "Personalization is on — answers will be tailored to you."
          : "Personalization is off — nothing new is learned from your questions.",
      );
    } catch {
      notify("err", "Could not change your personalization setting.");
      void load();
    } finally {
      setToggling(false);
    }
  };

  const onDelete = async () => {
    setDeleting(true);
    try {
      const res = await api.personalization.deleteMyData();
      notify("ok", `Deleted ${res.deleted} learned signal${res.deleted === 1 ? "" : "s"}.`);
      setConfirmingDelete(false);
      await load();
    } catch {
      notify("err", "Could not delete your personalization data — please try again.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className="pers" data-testid={testId} aria-label="Personalization">
      <header className="pers__head">
        <div>
          <h3 className="pers__title">For you</h3>
          <p className="pers__subtitle">
            What the assistant has learned from your own questions — per account.
          </p>
        </div>
        <button
          type="button"
          className="pers__close"
          onClick={onClose}
          aria-label="Close personalization panel"
          data-testid={testId ? `${testId}-close` : undefined}
        >
          ×
        </button>
      </header>

      {error ? (
        <StatusBanner
          kind="err"
          title="Could not load personalization"
          description={error}
          testId={testId ? `${testId}-error` : undefined}
          action={
            <Button variant="secondary" size="sm" loading={loading} onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      ) : null}

      {loading && !profile ? (
        <p className="pers__loading" data-testid={testId ? `${testId}-loading` : undefined}>
          Loading your profile…
        </p>
      ) : null}

      <div className="pers__toggle-row">
        <Field
          label="Personalization"
          helperText="When on, your questions shape the recommendations you see."
        >
          <input
            type="checkbox"
            role="switch"
            checked={enabled}
            disabled={toggling || (loading && !profile)}
            onChange={(e) => void onToggle(e.target.checked)}
            data-testid={testId ? `${testId}-toggle` : undefined}
          />
        </Field>
        <span className="pers__state" data-testid={testId ? `${testId}-state` : undefined}>
          {enabled ? "On" : "Off"}
        </span>
      </div>

      {profile ? (
        <div className="pers__profile" data-testid={testId ? `${testId}-profile` : undefined}>
          <div className="pers__stats">
            <span className="pers__stat">
              {profile.total_interactions} interaction{profile.total_interactions === 1 ? "" : "s"}
            </span>
            <span className="pers__stat pers__stat--muted">{formatLastActive(profile.last_active)}</span>
            {entityType ? <span className="pers__stat pers__stat--muted">Entity: {entityType}</span> : null}
            {taxYear ? <span className="pers__stat pers__stat--muted">Tax year: {taxYear}</span> : null}
          </div>
          {topDomains.length > 0 ? (
            <ul className="pers__domains">
              {topDomains.map(([domain, score]) => (
                <li className="pers__domain" key={domain}>
                  <span className="pers__domain-name">{domain}</span>
                  <span className="pers__domain-bar" aria-hidden>
                    <span
                      className="pers__domain-fill"
                      style={{ width: `${Math.max(2, Math.min(100, Math.round(score * 100)))}%` }}
                    />
                  </span>
                  <span className="pers__domain-score">{score.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="pers__empty">No topics learned yet — ask a few questions and they show up here.</p>
          )}
        </div>
      ) : null}

      <p className="pers__note">{HONEST_NOTE}</p>

      <div className="pers__danger">
        {confirmingDelete ? (
          <div className="pers__confirm" data-testid={testId ? `${testId}-confirm` : undefined}>
            <p className="pers__confirm-text">
              Delete every learned signal for this account? This cannot be undone.
            </p>
            <div className="pers__confirm-actions">
              <Button
                variant="danger"
                size="sm"
                loading={deleting}
                disabled={deleting}
                onClick={() => void onDelete()}
                data-testid={testId ? `${testId}-delete-confirm` : undefined}
              >
                Yes, delete my data
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={deleting}
                onClick={() => setConfirmingDelete(false)}
                data-testid={testId ? `${testId}-delete-cancel` : undefined}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmingDelete(true)}
            data-testid={testId ? `${testId}-delete` : undefined}
          >
            Delete my data
          </Button>
        )}
      </div>
    </section>
  );
}
