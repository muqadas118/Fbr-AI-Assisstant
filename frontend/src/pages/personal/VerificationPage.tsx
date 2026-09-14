import { useState, useCallback } from "react";
import { api, ApiError, NetworkError, type VerificationResponse } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Kv } from "@/components/ui/Kv";

type Tab = "ntn" | "filer" | "cnic" | "vendor";

function ResultCard({ result }: { result: VerificationResponse }) {
  return (
    <Card title="Verification Result" testId="verify-result-card">
      <div className="vault-result-header">
        <h3 className="vault-result-header__value">{result.value}</h3>
        <Tag variant={result.is_verified ? "ok" : "err"}>
          {result.is_verified ? "VERIFIED" : "NOT VERIFIED"}
        </Tag>
      </div>
      <p className="card__body-text">{result.message}</p>
      <Kv
        rows={[
          { key: "Request Type", value: result.request_type },
          { key: "Confidence", value: `${Math.round(result.confidence * 100)}%` },
          ...Object.entries((result.details ?? {}) as Record<string, unknown>).map(([k, v]) => ({
            key: k.replace(/_/g, " "),
            value: String(v ?? "—"),
          })),
        ]}
        testId="verify-result-kv"
      />
    </Card>
  );
}

function useVerifyTab(fn: (v: string) => Promise<VerificationResponse>) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const run = useCallback(async () => {
    if (!value.trim()) { setError("Value required"); return; }
    setLoading(true); setError(null); setResult(null);
    try { setResult(await fn(value.trim())); }
    catch (err) {
      setError(err instanceof ApiError || err instanceof NetworkError ? err.message : "Verification failed");
    } finally { setLoading(false); }
  }, [fn, value]);
  return { value, setValue, loading, error, result, run };
}

export function VerificationPage() {
  const [tab, setTab] = useState<Tab>("ntn");
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const t = useVerifyTab(tab === "ntn" ? api.verify.ntn : tab === "filer" ? api.verify.filer : tab === "cnic" ? api.verify.cnic : api.verify.vendor);
  const labels: Record<Tab, string> = { ntn: "NTN", filer: "Filer Status (ATL)", cnic: "CNIC", vendor: "Vendor NTN" };

  return (
    <ErrorBoundary>
      <div className="page page--verification">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Verification</div>
            <h2 className="page__title">Verification</h2>
          <p className="page__subtitle">Verify NTN, filer status, CNIC and vendors via backend verification center.</p>
          </div>
        </header>
        <div className="page__content">
          <div className="tabs page__tabs" data-testid="verify-tabs">
            {(Object.keys(labels) as Tab[]).map((k) => (
              <button key={k} className={`tab-btn${tab === k ? " tab-btn--active" : ""}`} onClick={() => setTab(k)} data-testid={`verify-tab-${k}`}>{labels[k]}</button>
            ))}
          </div>
          <section className="card" data-testid="verify-form-card">
          <form onSubmit={(e) => { e.preventDefault(); void t.run(); }} data-testid="verify-form">
            <Field label={labels[tab]} data-testid="verify-field">
              <input value={t.value} onChange={(e) => t.setValue(e.target.value)} placeholder={tab === "cnic" ? "35201-1234567-1" : "1234567-8"} data-testid="verify-input" />
            </Field>
            <div className="form__actions">
              <Button type="submit" variant="primary" loading={t.loading} disabled={t.loading} data-testid="verify-button">Verify</Button>
            </div>
          </form>
          </section>
          {t.error ? <StatusBanner kind="err" title="Verification failed" description={t.error} testId="verify-error" /> : null}
          {t.result ? <ResultCard result={t.result} /> : null}
          <StatusBanner kind="info" title="Offline check" description="Backend verification is format + checksum based (no live FBR portal yet)." testId="verify-offline-note" />
        </div>
      </div>
    </ErrorBoundary>
  );
}
