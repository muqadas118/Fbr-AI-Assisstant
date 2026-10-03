import { useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { useProfile } from "@/state/profile";

interface SettingsForm {
  displayName: string;
  ntn: string;
  cnic: string;
  email: string;
  language: string;
  timezone: string;
  emailNotifications: boolean;
  pushNotifications: boolean;
  smsNotifications: boolean;
  theme: "light" | "dark" | "system";
}

function initialForm(): SettingsForm {
  const profile = useProfile.getState();
  let saved: Partial<SettingsForm> = {};
  try {
    const raw = localStorage.getItem("fbr-settings");
    if (raw) saved = JSON.parse(raw) as Partial<SettingsForm>;
  } catch {
    saved = {};
  }
  return {
    displayName: profile.displayName || saved.displayName || "",
    ntn: profile.ntn || localStorage.getItem("fbr_ntn") || "",
    cnic: profile.cnic || "",
    email: profile.email || "",
    language: saved.language || "en",
    timezone: saved.timezone || "Asia/Karachi",
    emailNotifications: saved.emailNotifications ?? true,
    pushNotifications: saved.pushNotifications ?? true,
    smsNotifications: saved.smsNotifications ?? false,
    theme: saved.theme || "system",
  };
}

export function SettingsPage() {
  const [form, setForm] = useState<SettingsForm>(initialForm);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange =
    <K extends keyof SettingsForm>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value =
        e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const handleSave = useCallback(() => {
    setSaving(true);
    setSaved(false);
    setError(null);

    // Save identity to the shared profile store (+ legacy fbr_ntn key);
    // UI preferences stay in localStorage as local UI state only.
    setTimeout(() => {
      try {
        useProfile.getState().setProfile({
          displayName: form.displayName,
          ntn: form.ntn.trim(),
          cnic: form.cnic.trim(),
          email: form.email.trim(),
        });
        localStorage.setItem("fbr-settings", JSON.stringify(form));
        setSaved(true);
        setSaving(false);
      } catch {
        setError("Could not save settings. Please try again.");
        setSaving(false);
      }
    }, 500);
  }, [form]);

  return (
    <div className="page page--settings">
      <header className="page__header">
        <div>
          <div className="page__eyebrow page-eyebrow eyebrow">FBR · Settings</div>
          <h2 className="page__title">Profile / Settings</h2>
          <p className="page__subtitle">Display and notification preferences.</p>
        </div>
      </header>

      <div className="page__content">
        {error ? (
          <StatusBanner
            kind="err"
            title="Save failed"
            description={error}
            testId="settings-error"
          />
        ) : null}

        {saved ? (
          <StatusBanner
            kind="ok"
            title="Settings saved"
            description="Your preferences have been saved locally."
            testId="settings-saved"
          />
        ) : null}

        <Card title="Tax Identity" testId="settings-identity">
          <div className="settings-form grid grid--2">
            <Field label="NTN" helperText="National Tax Number — shared with Overview, Readiness & Vault">
              <input
                type="text"
                value={form.ntn}
                onChange={handleChange("ntn")}
                placeholder="e.g. 123456789"
                data-testid="settings-ntn"
              />
            </Field>

            <Field label="CNIC" helperText="Computerized National Identity Card number">
              <input
                type="text"
                value={form.cnic}
                onChange={handleChange("cnic")}
                placeholder="e.g. 1234567890123"
                data-testid="settings-cnic"
              />
            </Field>

            <Field label="Email" helperText="Contact email for notifications">
              <input
                type="email"
                value={form.email}
                onChange={handleChange("email")}
                placeholder="you@example.com"
                data-testid="settings-email"
              />
            </Field>
          </div>
        </Card>

        <Card title="Display Preferences" testId="settings-display">
          <div className="settings-form grid grid--2">
            <Field label="Display Name" helperText="How your name appears in the interface">
              <input
                type="text"
                value={form.displayName}
                onChange={handleChange("displayName")}
                placeholder="Your name"
                data-testid="settings-display-name"
              />
            </Field>

            <Field label="Language" helperText="Interface language">
              <Select
                value={form.language}
                onChange={(v) => setForm((prev) => ({ ...prev, language: v }))}
                testId="settings-language"
                ariaLabel="Interface language"
                options={[
                  { value: "en", label: "English" },
                  { value: "ur", label: "Urdu" },
                ]}
              />
            </Field>

            <Field label="Timezone" helperText="Used for deadline and reminder calculations">
              <Select
                value={form.timezone}
                onChange={(v) => setForm((prev) => ({ ...prev, timezone: v }))}
                testId="settings-timezone"
                ariaLabel="Timezone"
                options={[
                  { value: "Asia/Karachi", label: "Asia/Karachi (PKT)" },
                  { value: "Asia/Islamabad", label: "Asia/Islamabad (PKT)" },
                  { value: "UTC", label: "UTC" },
                ]}
              />
            </Field>

            <Field label="Theme" helperText="Visual theme">
              <Select
                value={form.theme}
                onChange={(v) => setForm((prev) => ({ ...prev, theme: v as SettingsForm["theme"] }))}
                testId="settings-theme"
                ariaLabel="Visual theme"
                options={[
                  { value: "system", label: "System" },
                  { value: "light", label: "Light" },
                  { value: "dark", label: "Dark" },
                ]}
              />
            </Field>
          </div>
        </Card>

        <Card title="Notification Preferences" testId="settings-notifications">
          <div className="settings-form">
            <Field label="Email Notifications" helperText="Receive notifications via email">
              <label className="settings-form__checkbox">
                <input
                  type="checkbox"
                  checked={form.emailNotifications}
                  onChange={handleChange("emailNotifications")}
                  data-testid="settings-email-notifications"
                />
                <span>Enable email notifications</span>
              </label>
            </Field>

            <Field label="Push Notifications" helperText="Receive push notifications in the browser">
              <label className="settings-form__checkbox">
                <input
                  type="checkbox"
                  checked={form.pushNotifications}
                  onChange={handleChange("pushNotifications")}
                  data-testid="settings-push-notifications"
                />
                <span>Enable push notifications</span>
              </label>
            </Field>

            <Field label="SMS Notifications" helperText="Receive notifications via SMS">
              <label className="settings-form__checkbox">
                <input
                  type="checkbox"
                  checked={form.smsNotifications}
                  onChange={handleChange("smsNotifications")}
                  data-testid="settings-sms-notifications"
                />
                <span>Enable SMS notifications</span>
              </label>
            </Field>
          </div>
        </Card>

        <div className="settings-form__actions">
          <Button
            variant="primary"
            loading={saving}
            disabled={saving}
            onClick={handleSave}
            data-testid="settings-save"
          >
            {saving ? "Saving…" : "Save Preferences"}
          </Button>
        </div>
      </div>
    </div>
  );
}