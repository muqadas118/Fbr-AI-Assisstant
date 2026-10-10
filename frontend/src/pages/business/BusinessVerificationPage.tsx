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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = "company" | "sales-tax" | "vendor" | "atl" | "cnic";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function boolTag(value: boolean, trueLabel = "Yes", falseLabel = "No"): React.ReactNode {
  return <Tag variant={value ? "ok" : "warn"}>{value ? trueLabel : falseLabel}</Tag>;
}

function confidenceTag(value: number): React.ReactNode {
  return (
    <Tag variant={value >= 0.8 ? "ok" : value >= 0.5 ? "warn" : "err"}>
      {Math.round(value * 100)}%
    </Tag>
  );
}

function verifiedBadge(response: VerificationResponse): React.ReactNode {
  return (
    <Tag variant={response.is_verified ? "ok" : "err"}>
      {response.is_verified ? "VERIFIED" : "NOT VERIFIED"}
    </Tag>
  );
}

function renderDetails(
  details: Record<string, unknown>,
): Array<{ key: string; value: React.ReactNode }> {
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
    return {
      key: k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      value: display,
    };
  });
}

function VerifyResultCard({ result }: { result: VerificationResponse }) {
  const details = result.details as Record<string, unknown> | undefined;

  return (
    <Card title="Verification Result" testId="biz-verify-result-card">
      <div className="vault-result-header">
        <h3 className="vault-result-header__value">{result.value}</h3>
        {verifiedBadge(result)}
      </div>
      <p className="card__body-text" style={{ marginBottom: "var(--s-4)" }}>
        {result.message}
      </p>
      <Kv
        rows={[
          { key: "Request Type", value: result.request_type },
          { key: "Verified", value: boolTag(result.is_verified) },
          { key: "Confidence", value: confidenceTag(result.confidence) },
          ...renderDetails(details ?? {}),
        ]}
        testId="biz-verify-result-kv"
      />
      {details?.warnings && Array.isArray(details.warnings) && (details.warnings as string[]).length > 0 ? (
        <>
          <hr className="divider" />
          <h4 style={{ fontSize: "14px", marginBottom: "var(--s-2)" }}>Warnings</h4>
          {(details.warnings as string[]).map((w, i) => (
            <StatusBanner key={i} kind="warn" title={w} testId={`biz-verify-warning-${i}`} />
          ))}
        </>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Tab 1: Company NTN Verification
// ---------------------------------------------------------------------------

function CompanyNtnTab() {
  const [ntn, setNtn] = useState("");
  const [regType, setRegType] = useState("ntn");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [ntnError, setNtnError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = useCallback((): boolean => {
    if (!ntn.trim()) {
      setNtnError("Company NTN / registration number is required");
      return false;
    }
    setNtnError(null);
    return true;
  }, [ntn]);

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.business(ntn.trim(), regType);
      setResult(resp);
      if (resp.is_verified) {
        notify("ok", `Company ${ntn} verified successfully.`);
      } else {
        notify("warn", `Company ${ntn} could not be verified.`);
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
  }, [validate, ntn, regType, notify]);

  return (
    <div className="vault-tab">
      <Card
        title="Verify Company NTN"
        subtitle="Confirm a business entity's NTN registration with FBR (Company, AOP, or Sole Proprietor)"
        testId="biz-company-verify-card"
      >
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-company-verify-form"
        >
          <Field label="Company NTN / Registration" error={ntnError ?? undefined} data-testid="biz-company-input-field">
            <input
              type="text"
              value={ntn}
              onChange={(e) => { setNtn(e.target.value); setNtnError(null); }}
              placeholder="e.g. 1234567-9"
              data-testid="biz-company-verify-input"
            />
          </Field>
          <Field label="Registration Type" data-testid="biz-company-regtype-field">
            <Select
              value={regType}
              onChange={setRegType}
              testId="biz-company-regtype-select"
              ariaLabel="Registration type"
              options={[
                { value: "ntn", label: "NTN" },
                { value: "secp_company", label: "SECP Company" },
                { value: "pra_registration", label: "PRA Registration" },
              ]}
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-company-verify-submit">
              {loading ? "Verifying…" : "Verify Company"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setNtn(""); setResult(null); setError(null); setNtnError(null); }}
              data-testid="biz-company-verify-reset"
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying company with FBR…" testId="biz-company-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Company verification failed" description={error} testId="biz-company-error" />
      ) : null}

      {result && !loading ? <VerifyResultCard result={result} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: Sales Tax Registration
// ---------------------------------------------------------------------------

function SalesTaxTab() {
  const [stn, setStn] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [stnError, setStnError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = useCallback((): boolean => {
    if (!stn.trim()) {
      setStnError("Sales Tax Registration Number is required");
      return false;
    }
    setStnError(null);
    return true;
  }, [stn]);

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.business(stn.trim(), "pra_registration");
      setResult(resp);
      if (resp.is_verified) {
        notify("ok", `Sales tax registration ${stn} verified.`);
      } else {
        notify("warn", `Sales tax registration ${stn} could not be verified.`);
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
  }, [validate, stn, notify]);

  return (
    <div className="vault-tab">
      <Card
        title="Verify Sales Tax Registration"
        subtitle="Check a business's active sales tax registration number with FBR"
        testId="biz-salestax-verify-card"
      >
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-salestax-verify-form"
        >
          <Field label="Sales Tax Registration No." error={stnError ?? undefined} data-testid="biz-salestax-input-field">
            <input
              type="text"
              value={stn}
              onChange={(e) => { setStn(e.target.value); setStnError(null); }}
              placeholder="e.g. 123456789"
              data-testid="biz-salestax-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-salestax-verify-submit">
              {loading ? "Verifying…" : "Verify Registration"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setStn(""); setResult(null); setError(null); setStnError(null); }}
              data-testid="biz-salestax-verify-reset"
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying sales tax registration…" testId="biz-salestax-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Sales tax verification failed" description={error} testId="biz-salestax-error" />
      ) : null}

      {result && !loading ? <VerifyResultCard result={result} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: Vendor Verification
// ---------------------------------------------------------------------------

function VendorTab() {
  const [vendorNtn, setVendorNtn] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [vendorError, setVendorError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = useCallback((): boolean => {
    if (!vendorNtn.trim()) {
      setVendorError("Vendor NTN is required");
      return false;
    }
    setVendorError(null);
    return true;
  }, [vendorNtn]);

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.vendor(vendorNtn.trim());
      setResult(resp);
      const details = resp.details as Record<string, unknown>;
      const isRegistered = details?.is_registered as boolean | undefined;
      if (isRegistered) {
        notify("ok", `Vendor ${vendorNtn} is registered.`);
      } else {
        notify("warn", `Vendor ${vendorNtn} may not be registered.`);
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
  }, [validate, vendorNtn, notify]);

  const details = result?.details as Record<string, unknown> | undefined;

  return (
    <div className="vault-tab">
      <Card
        title="Verify Vendor"
        subtitle="Check if a vendor is registered with FBR, their filer status, and WHT compliance"
        testId="biz-vendor-verify-card"
      >
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-vendor-verify-form"
        >
          <Field label="Vendor NTN" error={vendorError ?? undefined} data-testid="biz-vendor-input-field">
            <input
              type="text"
              value={vendorNtn}
              onChange={(e) => { setVendorNtn(e.target.value); setVendorError(null); }}
              placeholder="e.g. 1234567-9"
              data-testid="biz-vendor-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-vendor-verify-submit">
              {loading ? "Verifying…" : "Verify Vendor"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setVendorNtn(""); setResult(null); setError(null); setVendorError(null); }}
              data-testid="biz-vendor-verify-reset"
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying vendor with FBR…" testId="biz-vendor-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Vendor verification failed" description={error} testId="biz-vendor-error" />
      ) : null}

      {result && !loading ? (
        <>
          <Card title="Verification Result" testId="biz-vendor-result-card">
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
                { key: "Registered", value: boolTag(Boolean(details?.is_registered), "Yes", "No") },
                { key: "Active", value: boolTag(Boolean(details?.is_active), "Yes", "No") },
                { key: "Filer", value: boolTag(Boolean(details?.is_filer), "Active Filer", "Non-Filer") },
                { key: "Blacklisted", value: boolTag(Boolean(details?.is_blacklisted), "BLACKLISTED", "No") },
                { key: "Risk Score", value: details?.risk_score != null ? (
                    <Tag variant={(details?.risk_score as number) > 50 ? "err" : (details?.risk_score as number) > 20 ? "warn" : "ok"}>
                      {String(details?.risk_score)}/100
                    </Tag>
                  ) : "—" },
                { key: "WHT Rate", value: details?.wht_rate != null ? `${String(details?.wht_rate)}%` : "—" },
              ]}
              testId="biz-vendor-result-kv"
            />
            {details?.warnings && Array.isArray(details.warnings) && (details.warnings as string[]).length > 0 ? (
              <>
                <hr className="divider" />
                <h4 style={{ fontSize: "14px", marginBottom: "var(--s-2)" }}>Warnings</h4>
                {(details.warnings as string[]).map((w, i) => (
                  <StatusBanner key={i} kind="warn" title={w} testId={`biz-vendor-warning-${i}`} />
                ))}
              </>
            ) : null}
          </Card>
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: Active Taxpayer List (ATL)
// ---------------------------------------------------------------------------

function AtlTab() {
  const [ntn, setNtn] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ ntn: string; on_atl: boolean; filer_status: string; last_return: string } | null>(null);
  const [ntnError, setNtnError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = useCallback((): boolean => {
    if (!ntn.trim()) {
      setNtnError("Company NTN is required");
      return false;
    }
    setNtnError(null);
    return true;
  }, [ntn]);

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.checkAtl(ntn.trim());
      setResult(resp);
      if (resp.on_atl) {
        notify("ok", `NTN ${ntn} is on the Active Taxpayers List.`);
      } else {
        notify("warn", `NTN ${ntn} is not on the Active Taxpayers List.`);
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
  }, [validate, ntn, notify]);

  return (
    <div className="vault-tab">
      <Card
        title="Active Taxpayer List"
        subtitle="Confirm a business entity appears on FBR's Active Taxpayers List (ATL)"
        testId="biz-atl-verify-card"
      >
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-atl-verify-form"
        >
          <Field label="Company NTN" error={ntnError ?? undefined} data-testid="biz-atl-input-field">
            <input
              type="text"
              value={ntn}
              onChange={(e) => { setNtn(e.target.value); setNtnError(null); }}
              placeholder="e.g. 1234567-9"
              data-testid="biz-atl-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-atl-verify-submit">
              {loading ? "Checking…" : "Check ATL"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setNtn(""); setResult(null); setError(null); setNtnError(null); }}
              data-testid="biz-atl-verify-reset"
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Checking Active Taxpayers List…" testId="biz-atl-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="ATL check failed" description={error} testId="biz-atl-error" />
      ) : null}

      {result && !loading ? (
        <Card title="ATL Status" testId="biz-atl-result-card">
          <div className="vault-result-header">
            <h3 className="vault-result-header__value">{result.ntn}</h3>
            <Tag variant={result.on_atl ? "ok" : "err"}>
              {result.on_atl ? "ON ATL" : "NOT ON ATL"}
            </Tag>
          </div>
          <Kv
            rows={[
              { key: "Active Taxpayer", value: boolTag(result.on_atl) },
              { key: "Filer Status", value: <Tag variant={result.filer_status === "Filer" ? "ok" : "warn"}>{result.filer_status}</Tag> },
              { key: "Last Return Filed", value: result.last_return || "—" },
            ]}
            testId="biz-atl-result-kv"
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 5: Owner CNIC Verification
// ---------------------------------------------------------------------------

function OwnerCnicTab() {
  const [cnic, setCnic] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [cnicError, setCnicError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = useCallback((): boolean => {
    const cleaned = cnic.replace(/\D/g, "");
    if (!cnic.trim() || cleaned.length < 10) {
      setCnicError("Enter a valid CNIC (e.g. 1234567890123)");
      return false;
    }
    setCnicError(null);
    return true;
  }, [cnic]);

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.cnic(cnic.trim());
      setResult(resp);
      if (resp.is_verified) {
        notify("ok", `Owner CNIC ${cnic} verified.`);
      } else {
        notify("warn", `Owner CNIC ${cnic} could not be verified.`);
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
  }, [validate, cnic, notify]);

  return (
    <div className="vault-tab">
      <Card
        title="Verify Owner CNIC"
        subtitle="Confirm the identity and filer status of a business owner or partner"
        testId="biz-cnic-verify-card"
      >
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-cnic-verify-form"
        >
          <Field label="Owner CNIC" error={cnicError ?? undefined} data-testid="biz-cnic-input-field">
            <input
              type="text"
              value={cnic}
              onChange={(e) => { setCnic(e.target.value); setCnicError(null); }}
              placeholder="e.g. 1234567890123"
              data-testid="biz-cnic-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-cnic-verify-submit">
              {loading ? "Verifying…" : "Verify Owner"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setCnic(""); setResult(null); setError(null); setCnicError(null); }}
              data-testid="biz-cnic-verify-reset"
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying owner CNIC…" testId="biz-cnic-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Owner CNIC verification failed" description={error} testId="biz-cnic-error" />
      ) : null}

      {result && !loading ? <VerifyResultCard result={result} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export function BusinessVerificationPage() {
  const [activeTab, setActiveTab] = useState<Tab>("company");

  const tabs: { id: Tab; label: string }[] = [
    { id: "company", label: "Company NTN" },
    { id: "sales-tax", label: "Sales Tax Registration" },
    { id: "vendor", label: "Vendor NTN" },
    { id: "atl", label: "Active Taxpayer List" },
    { id: "cnic", label: "Owner CNIC" },
  ];

  return (
    <ErrorBoundary>
      <section className="page page--vault">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Verification</div>
            <h2 className="page__title">Business Verification</h2>
            <p className="page__subtitle">
              Verify business entities with FBR — company NTN, sales tax registration, vendor
              compliance, Active Taxpayers List, and owner CNIC.
            </p>
          </div>
        </header>

        <div className="page__tabs" role="tablist" data-testid="biz-verify-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={clsx("tab-btn", activeTab === tab.id && "tab-btn--active")}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`biz-verify-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="page__content" role="tabpanel">
          {activeTab === "company" && <CompanyNtnTab />}
          {activeTab === "sales-tax" && <SalesTaxTab />}
          {activeTab === "vendor" && <VendorTab />}
          {activeTab === "atl" && <AtlTab />}
          {activeTab === "cnic" && <OwnerCnicTab />}
        </div>
      </section>
    </ErrorBoundary>
  );
}