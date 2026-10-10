import { useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { useProfile } from "@/state/profile";

interface BusinessSettingsForm {
  companyName: string;
  businessNtn: string;
  strn: string;
  email: string;
  taxpayerType: string;
  timezone: string;
  emailNotifications: boolean;
  pushNotifications: boolean;
  teamAlerts: boolean;
}

function initialForm(): BusinessSettingsForm {
  const profile = useProfile.getState();
  let saved: Partial<BusinessSettingsForm> = {};
  try {
    const raw = localStorage.getItem("fbr-business-settings");
    if (raw) saved = JSON.parse(raw) as Partial<BusinessSettingsForm>;
  } catch {
    saved = {};
  }
  return {
    companyName: profile.displayName || saved.companyName || "",
    businessNtn: profile.ntn || localStorage.getItem("fbr_ntn") || "",
    strn: saved.strn || "",
    email: profile.email || "",
    taxpayerType: saved.taxpayerType || "company",
    timezone: saved.timezone || "Asia/Karachi",
    emailNotifications: saved.emailNotifications ?? true,
    pushNotifications: saved.pushNotifications ?? true,
    teamAlerts: saved.teamAlerts ?? true,
  };
}

export function BusinessSettingsPage() {
  const [form, setForm] = useState<BusinessSettingsForm>(initialForm);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange =
    <K extends keyof BusinessSettingsForm>(field: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value =
        e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };

  const handleSave = useCallback(() => {
    setSaving(true);
    setSaved(false);
    setError(null);
    setTimeout(() => {
      try {
        useProfile.getState().setProfile({
          displayName: form.companyName,
          ntn: form.businessNtn.trim(),
          email: form.email.trim(),
        });
        localStorage.setItem("fbr-business-settings", JSON.stringify(form));
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
          <div className="page__eyebrow page-eyebrow eyebrow">FBR · Business Settings</div>
          <h2 className="page__title">Business Settings</h2>
          <p className="page__subtitle">Organization profile and workspace preferences.</p>
        </div>
      </header>

      <div className="page__content">
        {error ? (
          <StatusBanner kind="err" title="Save failed" description={error} testId="biz-settings-error" />
        ) : null}

        {saved ? (
          <StatusBanner
            kind="ok"
            title="Settings saved"
            description="Your business preferences have been saved."
            testId="biz-settings-saved"
          />
        ) : null}

        <Card title="Organization Identity" testId="biz-settings-identity">
          <div className="settings-form grid grid--2">
            <Field label="Company Name" helperText="Registered business name">
              <input
                type="text"
                value={form.companyName}
                onChange={handleChange("companyName")}
                placeholder="e.g. Acme (Pvt) Ltd"
                data-testid="biz-settings-company"
              />
            </Field>

            <Field label="Business NTN" helperText="Shared with Overview, Health & Vault">
              <input
                type="text"
                value={form.businessNtn}
                onChange={handleChange("businessNtn")}
                placeholder="e.g. 123456789"
                data-testid="biz-settings-ntn"
              />
            </Field>

            <Field label="STRN" helperText="Sales Tax Registration Number (if registered)">
              <input
                type="text"
                value={form.strn}
                onChange={handleChange("strn")}
                placeholder="e.g. 3277876123456"
                data-testid="biz-settings-strn"
              />
            </Field>

            <Field label="Contact Email" helperText="For FBR correspondence and alerts">
              <input
                type="email"
                value={form.email}
                onChange={handleChange("email")}
                placeholder="finance@company.com"
                data-testid="biz-settings-email"
              />
            </Field>
          </div>
        </Card>

        <Card title="Workspace Preferences" testId="biz-settings-preferences">
          <div className="settings-form grid grid--2">
            <Field label="Taxpayer Type" helperText="Used for calendar and health defaults">
              <Select
                value={form.taxpayerType}
                onChange={(v) => setForm((prev) => ({ ...prev, taxpayerType: v }))}
                testId="biz-settings-taxpayer-type"
                ariaLabel="Taxpayer type"
                options={[
                  { value: "company", label: "Company" },
                  { value: "aop", label: "Association of Persons (AOP)" },
                  { value: "business", label: "Sole Proprietorship" },
                ]}
              />
            </Field>

            <Field label="Timezone" helperText="Used for deadline and reminder calculations">
              <Select
                value={form.timezone}
                onChange={(v) => setForm((prev) => ({ ...prev, timezone: v }))}
                testId="biz-settings-timezone"
                ariaLabel="Timezone"
                options={[
                  { value: "Asia/Karachi", label: "Asia/Karachi (PKT)" },
                  { value: "UTC", label: "UTC" },
                ]}
              />
            </Field>
          </div>
        </Card>

        <Card title="Notification Preferences" testId="biz-settings-notifications">
          <div className="settings-form">
            <Field label="Email Notifications" helperText="Receive filing reminders via email">
              <label className="settings-form__checkbox">
                <input
                  type="checkbox"
                  aria-label="Enable email notifications"
                  checked={form.emailNotifications}
                  onChange={handleChange("emailNotifications")}
                  data-testid="biz-settings-email-notifications"
                />
                <span>Enable email notifications</span>
              </label>
            </Field>

            <Field label="Push Notifications" helperText="Browser push alerts for deadlines">
              <label className="settings-form__checkbox">
                <input
                  type="checkbox"
                  aria-label="Enable push notifications"
                  checked={form.pushNotifications}
                  onChange={handleChange("pushNotifications")}
                  data-testid="biz-settings-push-notifications"
                />
                <span>Enable push notifications</span>
              </label>
            </Field>

            <Field label="Team Alerts" helperText="Notify team members on shared deadlines">
              <label className="settings-form__checkbox">
                <input
                  type="checkbox"
                  aria-label="Enable team alerts"
                  checked={form.teamAlerts}
                  onChange={handleChange("teamAlerts")}
                  data-testid="biz-settings-team-alerts"
                />
                <span>Enable team alerts</span>
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
            data-testid="biz-settings-save"
          >
            {saving ? "Saving…" : "Save Preferences"}
          </Button>
        </div>
      </div>
    </div>
  );
}
