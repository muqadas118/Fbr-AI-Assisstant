import { useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";

interface SettingsForm {
  displayName: string;
  language: string;
  timezone: string;
  emailNotifications: boolean;
  pushNotifications: boolean;
  smsNotifications: boolean;
  theme: "light" | "dark" | "system";
}

export function SettingsPage() {
  const [form, setForm] = useState<SettingsForm>({
    displayName: "",
    language: "en",
    timezone: "Asia/Karachi",
    emailNotifications: true,
    pushNotifications: true,
    smsNotifications: false,
    theme: "system",
  });
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

    // For Part 1: no dedicated settings endpoint exists yet.
    // Save to localStorage as a local UI state only.
    setTimeout(() => {
      try {
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
        <h2 className="page__title">Profile / Settings</h2>
        <p className="page__subtitle">Display and notification preferences.</p>
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

        <Card title="Display Preferences" testId="settings-display">
          <div className="settings-form">
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
              <select
                value={form.language}
                onChange={handleChange("language")}
                data-testid="settings-language"
              >
                <option value="en">English</option>
                <option value="ur">Urdu</option>
              </select>
            </Field>

            <Field label="Timezone" helperText="Used for deadline and reminder calculations">
              <select
                value={form.timezone}
                onChange={handleChange("timezone")}
                data-testid="settings-timezone"
              >
                <option value="Asia/Karachi">Asia/Karachi (PKT)</option>
                <option value="Asia/Islamabad">Asia/Islamabad (PKT)</option>
                <option value="UTC">UTC</option>
              </select>
            </Field>

            <Field label="Theme" helperText="Visual theme">
              <select
                value={form.theme}
                onChange={handleChange("theme")}
                data-testid="settings-theme"
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
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