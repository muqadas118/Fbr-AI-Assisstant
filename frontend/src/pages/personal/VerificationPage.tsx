import { useState, useCallback } from "react";
import clsx from "clsx";
import {
  api,
  ApiError,
  NetworkError,
  type VerificationResponse,
} from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Loading } from "@/components/shell/Loading";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";
import { useProfile } from "@/state/profile";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = "ntn" | "filer" | "cnic" | "vendor" | "business" | "batch";

interface BatchRequest {
  key: string;
  type: string;
  value: string;
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function boolTag(value: boolean, trueLabel = "Yes", falseLabel = "No"): React.ReactNode {
  return <Tag variant={value ? "ok" : "warn"}>{value ? trueLabel : falseLabel}</Tag>;
}

function verifiedBadge(response: VerificationResponse): React.ReactNode {
  return (
    <Tag variant={response.is_verified ? "ok" : "err"}>
      {response.is_verified ? "VERIFIED" : "NOT VERIFIED"}
    </Tag>
  );
}

function renderDetails(details: Record<string, unknown>): Array<{ key: string; value: React.ReactNode }> {
  return Object.entries(details).map(([k, v]) => {
    let display: React.ReactNode;
    if (typeof v === "boolean") {
      display = <Tag variant={v ? "ok" : "warn"}>{v ? "Yes" : "No"}</Tag>;
    } else if (typeof v === "number") {
      display = v.toLocaleString("en-US");
    } else if (Array.isArray(v)) {
      display = v.length > 0 ? v.join(", ") : "—";
    } else if (v === null || v === undefined) {
      display = "—";
    } else {
      display = String(v);
    }
    return { key: k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()), value: display };
  });
}

function confidenceTag(confidence: number): React.ReactNode {
  return (
    <Tag variant={confidence >= 0.8 ? "ok" : confidence >= 0.5 ? "warn" : "err"}>
      {Math.round(confidence * 100)}%
    </Tag>
  );
}

// ---------------------------------------------------------------------------
// Result card (shared by all single checks)
// ---------------------------------------------------------------------------

function ResultCard({ result, testId }: { result: VerificationResponse; testId: string }) {
  return (
    <Card title="Verification Result" testId={testId}>
      <div className="vault-result-header">
        <h3 className="vault-result-header__value">{result.value}</h3>
        {verifiedBadge(result)}
      </div>
      <p className="card__body-text" style={{ marginBottom: "var(--s-4)" }}>{result.message}</p>
      <Kv
        rows={[
          { key: "Request Type", value: result.request_type },
          { key: "Verified", value: boolTag(result.is_verified) },
          { key: "Confidence", value: confidenceTag(result.confidence) },
          ...renderDetails((result.details ?? {}) as Record<string, unknown>),
        ]}
        testId={`${testId}-kv`}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Shared single-check hook
// ---------------------------------------------------------------------------

interface CheckConfig {
  label: string;
  placeholder: string;
  subtitle?: string;
  initialValue?: string;
  validate: (value: string) => string | null;
  run: (value: string) => Promise<VerificationResponse>;
  onVerified?: (value: string) => void;
}

function useSingleCheck(config: CheckConfig) {
  const [value, setValue] = useState(config.initialValue ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const { show: notify } = useNotification();

  const submit = useCallback(async () => {
    const problem = config.validate(value);
    if (problem) {
      setFieldError(problem);
      return;
    }
    setFieldError(null);
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await config.run(value.trim());
      setResult(resp);
      config.onVerified?.(value.trim());
      if (resp.is_verified) {
        notify("ok", `${config.label} ${value.trim()} verified.`);
      } else {
        notify("warn", `${config.label} ${value.trim()} could not be verified.`);
      }
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, value, notify]);

  const reset = useCallback(() => {
    setValue("");
    setResult(null);
    setError(null);
    setFieldError(null);
  }, []);

  return {
    value, setValue, loading, error, fieldError, result, submit, reset,
    label: config.label, placeholder: config.placeholder, subtitle: config.subtitle,
  };
}

function SingleCheckForm({
  check,
  testPrefix,
}: {
  check: ReturnType<typeof useSingleCheck>;
  testPrefix: string;
}) {
  return (
    <>
      <Card title={`Verify ${check.label}`} subtitle={check.subtitle} testId={`${testPrefix}-card`}>
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void check.submit(); }}
          data-testid={`${testPrefix}-form`}
        >
          <Field label={check.label} error={check.fieldError ?? undefined} data-testid={`${testPrefix}-field`}>
            <input
              type="text"
              value={check.value}
              onChange={(e) => { check.setValue(e.target.value); }}
              placeholder={check.placeholder}
              data-testid={`${testPrefix}-input`}
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={check.loading} disabled={check.loading} data-testid={`${testPrefix}-submit`}>
              {check.loading ? "Verifying…" : `Verify ${check.label}`}
            </Button>
            <Button type="button" variant="ghost" onClick={check.reset} data-testid={`${testPrefix}-reset`}>
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {check.loading ? <Loading label="Verifying with FBR…" testId={`${testPrefix}-loading`} /> : null}

      {check.error ? (
        <StatusBanner kind="err" title={`${check.label} verification failed`} description={check.error} testId={`${testPrefix}-error`} />
      ) : null}

      {check.result && !check.loading ? (
        <ResultCard result={check.result} testId={`${testPrefix}-result-card`} />
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Tab 1: NTN
// ---------------------------------------------------------------------------

function NtnTab() {
  const check = useSingleCheck({
    label: "NTN",
    placeholder: "e.g. 1234567-9",
    subtitle: "Check if a Taxpayer Identification Number is registered with FBR",
    initialValue: useProfile.getState().ntn || localStorage.getItem("fbr_ntn") || "",
    validate: (v) => (v.trim() ? null : "NTN is required"),
    run: (v) => api.verify.ntn(v),
    onVerified: (v) => useProfile.getState().setNtn(v),
  });
  return <SingleCheckForm check={check} testPrefix="ntn" />;
}

// ---------------------------------------------------------------------------
// Tab 2: Filer Status (ATL)
// ---------------------------------------------------------------------------

function FilerTab() {
  const check = useSingleCheck({
    label: "Filer Status",
    placeholder: "e.g. 1234567-9",
    subtitle: "Check Active Taxpayers List (ATL) status and filer details for an NTN",
    validate: (v) => (v.trim() ? null : "NTN is required"),
    run: (v) => api.verify.filer(v),
  });
  return <SingleCheckForm check={check} testPrefix="filer" />;
}

// ---------------------------------------------------------------------------
// Tab 3: CNIC
// ---------------------------------------------------------------------------

function CnicTab() {
  const check = useSingleCheck({
    label: "CNIC",
    placeholder: "e.g. 1234567890123",
    subtitle: "Check filer status and identity details for a Computerized National Identity Card",
    validate: (v) => {
      const cleaned = v.replace(/\D/g, "");
      if (!v.trim() || cleaned.length < 10) return "Enter a valid CNIC (e.g. 1234567890123)";
      return null;
    },
    run: (v) => api.verify.cnic(v),
    onVerified: (v) => useProfile.getState().setCnic(v),
  });
  return <SingleCheckForm check={check} testPrefix="cnic" />;
}

// ---------------------------------------------------------------------------
// Tab 4: Vendor
// ---------------------------------------------------------------------------

function VendorTab() {
  const check = useSingleCheck({
    label: "Vendor",
    placeholder: "e.g. 1234567-9",
    subtitle: "Check if a vendor is registered with FBR, their filer status, and WHT compliance",
    validate: (v) => (v.trim() ? null : "Vendor NTN is required"),
    run: (v) => api.verify.vendor(v),
  });
  return <SingleCheckForm check={check} testPrefix="vendor" />;
}

// ---------------------------------------------------------------------------
// Tab 5: Business Registration
// ---------------------------------------------------------------------------

function BusinessTab() {
  const [regType, setRegType] = useState("ntn");
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const { show: notify } = useNotification();

  const submit = useCallback(async () => {
    if (!value.trim()) {
      setFieldError("Registration number is required");
      return;
    }
    setFieldError(null);
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.business(value.trim(), regType);
      setResult(resp);
      if (resp.is_verified) {
        notify("ok", `Registration ${value.trim()} verified.`);
      } else {
        notify("warn", `Registration ${value.trim()} could not be verified.`);
      }
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }, [value, regType, notify]);

  const reset = useCallback(() => {
    setValue("");
    setRegType("ntn");
    setResult(null);
    setError(null);
    setFieldError(null);
  }, []);

  return (
    <>
      <Card
        title="Verify Business Registration"
        subtitle="Verify a business registration number (NTN, SECP company, or PRA registration) with FBR"
        testId="business-verify-card"
      >
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="business-verify-form"
        >
          <div className="grid grid--2">
            <Field label="Registration Number" error={fieldError ?? undefined} data-testid="business-number-field">
              <input
                type="text"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="e.g. 1234567-9"
                data-testid="business-verify-input"
              />
            </Field>
            <Field label="Registration Type" data-testid="business-type-field">
              <Select
                value={regType}
                onChange={setRegType}
                testId="business-type-select"
                ariaLabel="Registration type"
                options={[
                  { value: "ntn", label: "NTN" },
                  { value: "secp_company", label: "SECP Company" },
                  { value: "pra_registration", label: "PRA Registration" },
                ]}
              />
            </Field>
          </div>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="business-verify-submit">
              {loading ? "Verifying…" : "Verify Business"}
            </Button>
            <Button type="button" variant="ghost" onClick={reset} data-testid="business-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying business with FBR…" testId="business-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Business verification failed" description={error} testId="business-error" />
      ) : null}

      {result && !loading ? <ResultCard result={result} testId="business-result-card" /> : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Tab 6: Batch Verification
// ---------------------------------------------------------------------------

const BATCH_TYPES = ["ntn", "filer", "cnic", "vendor"] as const;

function BatchTab() {
  const [rows, setRows] = useState<BatchRequest[]>([
    { key: crypto.randomUUID(), type: "ntn", value: "" },
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<VerificationResponse[] | null>(null);
  const { show: notify } = useNotification();

  const addRow = useCallback(() => {
    setRows((prev) => [
      ...prev,
      { key: crypto.randomUUID(), type: "ntn", value: "" },
    ]);
  }, []);

  const removeRow = useCallback((key: string) => {
    setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.key !== key) : prev));
  }, []);

  const updateRow = useCallback((key: string, patch: Partial<BatchRequest>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }, []);

  const submit = useCallback(async () => {
    const filled = rows.filter((r) => r.value.trim());
    if (filled.length === 0) {
      setError("Add at least one value to verify.");
      return;
    }
    setError(null);
    setResults(null);
    setLoading(true);
    try {
      const resp = await api.verify.batch(filled.map((r) => ({ type: r.type, value: r.value.trim() })));
      setResults(resp);
      const verified = resp.filter((r) => r.is_verified).length;
      notify(verified === resp.length ? "ok" : "warn", `${verified} of ${resp.length} batch entries verified.`);
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }, [rows, notify]);

  return (
    <>
      <Card
        title="Batch Verification"
        subtitle="Verify up to 50 NTN / filer / CNIC / vendor values in one request"
        testId="batch-verify-card"
      >
        <div className="verify-batch__rows" data-testid="batch-rows">
          {rows.map((row, i) => (
            <div key={row.key} className="verify-batch__row" data-testid={`batch-row-${i}`}>
              <Select
                value={row.type}
                onChange={(t) => updateRow(row.key, { type: t })}
                testId={`batch-type-${i}`}
                ariaLabel={`Type for row ${i + 1}`}
                options={[...BATCH_TYPES]}
              />
              <input
                type="text"
                className="verify-batch__value"
                value={row.value}
                onChange={(e) => updateRow(row.key, { value: e.target.value })}
                placeholder={row.type === "cnic" ? "CNIC e.g. 1234567890123" : "NTN e.g. 1234567-9"}
                data-testid={`batch-value-${i}`}
                aria-label={`Value for row ${i + 1}`}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeRow(row.key)}
                disabled={rows.length === 1}
                data-testid={`batch-remove-${i}`}
                aria-label={`Remove row ${i + 1}`}
              >
                ✕
              </Button>
            </div>
          ))}
        </div>

        <div className="form__actions">
          <Button type="button" variant="ghost" size="sm" onClick={addRow} disabled={rows.length >= 50} data-testid="batch-add-row">
            + Add Row
          </Button>
        </div>

        <div className="form__actions">
          <Button type="button" variant="primary" loading={loading} disabled={loading} onClick={() => void submit()} data-testid="batch-verify-submit">
            {loading ? "Verifying…" : `Verify ${rows.filter((r) => r.value.trim()).length || 0} value${rows.filter((r) => r.value.trim()).length === 1 ? "" : "s"}`}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => { setRows([{ key: crypto.randomUUID(), type: "ntn", value: "" }]); setResults(null); setError(null); }}
            data-testid="batch-verify-reset"
          >
            Clear
          </Button>
        </div>
      </Card>

      {loading ? <Loading label="Running batch verification…" testId="batch-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Batch verification failed" description={error} testId="batch-error" />
      ) : null}

      {results && !loading ? (
        <Card
          title={`Batch Results — ${results.filter((r) => r.is_verified).length}/${results.length} verified`}
          testId="batch-result-card"
        >
          <div className="verify-batch__results">
            {results.map((r, i) => (
              <div key={i} className={clsx("verify-batch__result-row", !r.is_verified && "verify-batch__result-row--failed")} data-testid={`batch-result-${i}`}>
                <span className="verify-batch__result-value">{r.value}</span>
                <Tag variant={r.request_type === "cnic" ? "default" : "accent"}>{r.request_type}</Tag>
                {verifiedBadge(r)}
                <span className="verify-batch__result-msg">{r.message}</span>
              </div>
            ))}
          </div>
        </Card>
        ) : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS: { id: Tab; label: string }[] = [
  { id: "ntn", label: "NTN" },
  { id: "filer", label: "Filer Status (ATL)" },
  { id: "cnic", label: "CNIC" },
  { id: "vendor", label: "Vendor" },
  { id: "business", label: "Business Reg." },
  { id: "batch", label: "Batch" },
];

export function VerificationPage() {
  const [activeTab, setActiveTab] = useState<Tab>("ntn");

  return (
    <ErrorBoundary>
      <section className="page page--verification">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Verification Center</div>
            <h2 className="page__title">Verification Center</h2>
            <p className="page__subtitle">
              NTN, filer (ATL), CNIC, vendor, and business registration checks — one at a time or in batch.
            </p>
          </div>
        </header>

        <div className="page__tabs" role="tablist" data-testid="verify-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={clsx("tab-btn", activeTab === tab.id && "tab-btn--active")}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`verify-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="page__content" role="tabpanel">
          {activeTab === "ntn" && <NtnTab />}
          {activeTab === "filer" && <FilerTab />}
          {activeTab === "cnic" && <CnicTab />}
          {activeTab === "vendor" && <VendorTab />}
          {activeTab === "business" && <BusinessTab />}
          {activeTab === "batch" && <BatchTab />}

          <StatusBanner
            kind="info"
            title="Honest verification mode"
            description="Results come from the backend verification center's honest-unavailable contract: format and checksum validation with a clear 'unavailable' status — no fabricated registry data until a live FBR portal connection is configured."
            testId="verify-offline-note"
          />
        </div>
      </section>
    </ErrorBoundary>
  );
}
