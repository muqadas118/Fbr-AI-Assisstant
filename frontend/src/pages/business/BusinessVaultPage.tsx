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
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";
import { useProfile } from "@/state/profile";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Tab = "vault" | "ntn" | "business" | "vendor";

interface VaultFile {
  id: string;
  filename: string;
  type: string;
  size: string;
  date: string;
  secure: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

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

// ---------------------------------------------------------------------------
// Tab 1: Business Tax Vault
// ---------------------------------------------------------------------------

function VaultTab() {
  const [files, setFiles] = useState<VaultFile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newFilename, setNewFilename] = useState("");
  const [newType, setNewType] = useState("Sales Tax Return");
  const [newContent, setNewContent] = useState("");

  const handleAdd = useCallback(() => {
    if (!newFilename.trim()) return;
    const file: VaultFile = {
      id: `vault-${Date.now()}`,
      filename: newFilename.trim(),
      type: newType,
      size: `${newContent.length} chars`,
      date: new Date().toISOString(),
      secure: true,
    };
    setFiles((prev) => [file, ...prev]);
    setNewFilename("");
    setNewType("Sales Tax Return");
    setNewContent("");
    setShowAdd(false);
  }, [newFilename, newType, newContent]);

  const handleDelete = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
    if (selectedId === id) setSelectedId(null);
  }, [selectedId]);

  const selected = files.find((f) => f.id === selectedId) ?? null;

  return (
    <div className="vault-tab">
      <div className="vault-toolbar">
        <Button variant="primary" size="sm" onClick={() => setShowAdd(true)} data-testid="biz-vault-add-btn">
          + Add Business Document
        </Button>
        <span className="small muted">{files.length} document{files.length !== 1 ? "s" : ""} in business vault</span>
      </div>

      {showAdd && (
        <Card title="Add Document to Business Vault" testId="biz-vault-add-card">
          <form
            className="vault-add-form"
            onSubmit={(e) => { e.preventDefault(); void handleAdd(); }}
            data-testid="biz-vault-add-form"
          >
            <div className="grid grid--2">
              <Field label="Filename" data-testid="biz-vault-add-filename">
                <input
                  type="text"
                  value={newFilename}
                  onChange={(e) => setNewFilename(e.target.value)}
                  placeholder="e.g. ST_RETURN_JUL_2024.pdf"
                  required
                  data-testid="biz-vault-add-filename-input"
                />
              </Field>
              <Field label="Document Type" data-testid="biz-vault-add-type">
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  data-testid="biz-vault-add-type-select"
                >
                  <option>Sales Tax Return</option>
                  <option>Withholding (WHT) Statement</option>
                  <option>Company Income Tax Return</option>
                  <option>Input Tax Credit (ITC) Sheet</option>
                  <option>Sales Tax Invoice</option>
                  <option>Supplier/Vendor Invoice</option>
                  <option>Federal Excise Return</option>
                  <option>Corporate Registration / NTN</option>
                  <option>Bank Statement</option>
                  <option>Business Contract</option>
                  <option>Other</option>
                </select>
              </Field>
            </div>
            <Field label="Content / Notes" data-testid="biz-vault-add-content">
              <textarea
                rows={4}
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="Optional notes or summary of the business document…"
                data-testid="biz-vault-add-content-input"
              />
            </Field>
            <div className="form__actions">
              <Button type="submit" variant="primary" data-testid="biz-vault-add-submit">
                Add to Vault
              </Button>
              <Button type="button" variant="ghost" onClick={() => setShowAdd(false)} data-testid="biz-vault-add-cancel">
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {files.length === 0 && !showAdd ? (
        <StatusBanner
          kind="info"
          title="Business vault is empty"
          description="Add your first business tax document to the secure vault above."
          testId="biz-vault-empty"
        />
      ) : (
        <div className="vault-table-wrap">
          <table className="vault-table" data-testid="biz-vault-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Type</th>
                <th>Size</th>
                <th>Date Added</th>
                <th>Secure</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr
                  key={f.id}
                  className={clsx(selectedId === f.id && "vault-table__row--selected")}
                  onClick={() => setSelectedId(f.id === selectedId ? null : f.id)}
                  data-testid={`biz-vault-row-${f.id}`}
                >
                  <td className="vault-table__name">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    {f.filename}
                  </td>
                  <td><Tag variant="default">{f.type}</Tag></td>
                  <td className="mono small">{f.size}</td>
                  <td className="small">{formatDate(f.date)}</td>
                  <td>{boolTag(f.secure, "Encrypted", "Unencrypted")}</td>
                  <td>
                    <div className="vault-table__actions">
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setSelectedId(f.id); }} data-testid={`biz-vault-view-${f.id}`}>
                        View
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleDelete(f.id); }} data-testid={`biz-vault-delete-${f.id}`}>
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <Card title={`Document: ${selected.filename}`} testId="biz-vault-detail-card">
          <Kv
            rows={[
              { key: "Filename", value: selected.filename },
              { key: "Type", value: <Tag variant="default">{selected.type}</Tag> },
              { key: "Size", value: selected.size },
              { key: "Date Added", value: formatDate(selected.date) },
              { key: "Secure Storage", value: boolTag(selected.secure) },
            ]}
            testId="biz-vault-detail-kv"
          />
          <div className="form__actions" style={{ marginTop: "var(--s-4)" }}>
            <Button variant="ghost" size="sm" onClick={() => setSelectedId(null)} data-testid="biz-vault-detail-close">
              Close
            </Button>
            <Button variant="danger" size="sm" onClick={() => { handleDelete(selected.id); }} data-testid="biz-vault-detail-delete">
              Delete
            </Button>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: Verify Company NTN
// ---------------------------------------------------------------------------

function NtnTab() {
  const [ntn, setNtn] = useState(() => useProfile.getState().ntn || localStorage.getItem("fbr_ntn") || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [ntnError, setNtnError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = (): boolean => {
    if (!ntn.trim()) {
      setNtnError("Company NTN is required");
      return false;
    }
    setNtnError(null);
    return true;
  };

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.ntn(ntn.trim());
      setResult(resp);
      useProfile.getState().setNtn(ntn.trim());
      if (resp.is_verified) {
        notify("ok", `Company NTN ${ntn} verified successfully.`);
      } else {
        notify("warn", `Company NTN ${ntn} could not be verified.`);
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
  }, [ntn, notify]);

  return (
    <div className="vault-tab">
      <Card title="Verify Company NTN" subtitle="Check if a business entity's Taxpayer Identification Number is registered with FBR" testId="biz-ntn-verify-card">
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-ntn-verify-form"
        >
          <Field label="Company NTN" error={ntnError ?? undefined} data-testid="biz-ntn-input-field">
            <input
              type="text"
              value={ntn}
              onChange={(e) => { setNtn(e.target.value); setNtnError(null); }}
              placeholder="e.g. 1234567-9"
              data-testid="biz-ntn-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-ntn-verify-submit">
              {loading ? "Verifying…" : "Verify Company NTN"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setNtn(""); setResult(null); setError(null); setNtnError(null); }} data-testid="biz-ntn-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying company NTN with FBR…" testId="biz-ntn-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Company NTN verification failed" description={error} testId="biz-ntn-error" />
      ) : null}

      {result && !loading ? (
        <Card title="Verification Result" testId="biz-ntn-result-card">
          <div className="vault-result-header">
            <h3 className="vault-result-header__value">{result.value}</h3>
            {verifiedBadge(result)}
          </div>
          <p className="card__body-text" style={{ marginBottom: "var(--s-4)" }}>{result.message}</p>
          <Kv
            rows={[
              { key: "Request Type", value: result.request_type },
              { key: "Verified", value: boolTag(result.is_verified) },
              { key: "Confidence", value: <Tag variant={result.confidence >= 0.8 ? "ok" : result.confidence >= 0.5 ? "warn" : "err"}>{Math.round(result.confidence * 100)}%</Tag> },
              ...renderDetails(result.details),
            ]}
            testId="biz-ntn-result-kv"
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: Verify Business Registration
// ---------------------------------------------------------------------------

function BusinessTab() {
  const [regNumber, setRegNumber] = useState("");
  const [regType, setRegType] = useState("ntn");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [regError, setRegError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = (): boolean => {
    if (!regNumber.trim()) {
      setRegError("Registration number is required");
      return false;
    }
    setRegError(null);
    return true;
  };

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.business(regNumber.trim(), regType);
      setResult(resp);
      if (resp.is_verified) {
        notify("ok", `Business registration ${regNumber} verified.`);
      } else {
        notify("warn", `Business registration ${regNumber} could not be verified.`);
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
  }, [regNumber, regType, notify]);

  return (
    <div className="vault-tab">
      <Card title="Verify Business Registration" subtitle="Check the sales tax / registration status of a business entity with FBR" testId="biz-reg-verify-card">
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-reg-verify-form"
        >
          <div className="grid grid--2">
            <Field label="Registration Number" error={regError ?? undefined} data-testid="biz-reg-input-field">
              <input
                type="text"
                value={regNumber}
                onChange={(e) => { setRegNumber(e.target.value); setRegError(null); }}
                placeholder="e.g. 1234567-9"
                data-testid="biz-reg-verify-input"
              />
            </Field>
            <Field label="Registration Type" data-testid="biz-reg-type-field">
              <select
                value={regType}
                onChange={(e) => setRegType(e.target.value)}
                data-testid="biz-reg-type-select"
              >
                <option value="ntn">NTN</option>
                <option value="strn">STRN (Sales Tax)</option>
              </select>
            </Field>
          </div>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="biz-reg-verify-submit">
              {loading ? "Verifying…" : "Verify Business"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setRegNumber(""); setResult(null); setError(null); setRegError(null); }} data-testid="biz-reg-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying business registration with FBR…" testId="biz-reg-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Business registration verification failed" description={error} testId="biz-reg-error" />
      ) : null}

      {result && !loading ? (
        <Card title="Verification Result" testId="biz-reg-result-card">
          <div className="vault-result-header">
            <h3 className="vault-result-header__value">{result.value}</h3>
            {verifiedBadge(result)}
          </div>
          <p className="card__body-text" style={{ marginBottom: "var(--s-4)" }}>{result.message}</p>
          <Kv
            rows={[
              { key: "Request Type", value: result.request_type },
              { key: "Verified", value: boolTag(result.is_verified) },
              { key: "Confidence", value: <Tag variant={result.confidence >= 0.8 ? "ok" : result.confidence >= 0.5 ? "warn" : "err"}>{Math.round(result.confidence * 100)}%</Tag> },
              ...renderDetails(result.details),
            ]}
            testId="biz-reg-result-kv"
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: Verify Supplier / Vendor
// ---------------------------------------------------------------------------

function VendorTab() {
  const [vendorNtn, setVendorNtn] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [vendorError, setVendorError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = (): boolean => {
    if (!vendorNtn.trim()) {
      setVendorError("Supplier/Vendor NTN is required");
      return false;
    }
    setVendorError(null);
    return true;
  };

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
        notify("ok", `Supplier ${vendorNtn} is registered.`);
      } else {
        notify("warn", `Supplier ${vendorNtn} may not be registered.`);
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
  }, [vendorNtn, notify]);

  const details = result?.details as Record<string, unknown> | undefined;

  return (
    <div className="vault-tab">
      <Card title="Verify Supplier / Vendor" subtitle="Check if a supplier is registered with FBR, their filer status, and WHT compliance before booking purchases" testId="biz-vendor-verify-card">
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="biz-vendor-verify-form"
        >
          <Field label="Supplier / Vendor NTN" error={vendorError ?? undefined} data-testid="biz-vendor-input-field">
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
              {loading ? "Verifying…" : "Verify Supplier"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setVendorNtn(""); setResult(null); setError(null); setVendorError(null); }} data-testid="biz-vendor-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying supplier with FBR…" testId="biz-vendor-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Supplier verification failed" description={error} testId="biz-vendor-error" />
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
                { key: "Confidence", value: <Tag variant={result.confidence >= 0.8 ? "ok" : result.confidence >= 0.5 ? "warn" : "err"}>{Math.round(result.confidence * 100)}%</Tag> },
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
// Main Page
// ---------------------------------------------------------------------------

export function BusinessVaultPage() {
  const [activeTab, setActiveTab] = useState<Tab>("vault");

  const tabs: { id: Tab; label: string }[] = [
    { id: "vault", label: "Business Vault" },
    { id: "ntn", label: "Verify Company NTN" },
    { id: "business", label: "Verify Business" },
    { id: "vendor", label: "Verify Supplier" },
  ];

  return (
    <ErrorBoundary>
      <section className="page page--vault">
        <header className="page__header">
          <div>
            <h2 className="page__title">Business Tax Vault</h2>
            <p className="page__subtitle">
              Secure storage for business tax documents and FBR verification tools — company NTN, business registration, and supplier/vendor checks.
            </p>
          </div>
        </header>

        <div className="page__tabs" role="tablist" data-testid="biz-vault-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={clsx("tab-btn", activeTab === tab.id && "tab-btn--active")}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`biz-vault-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="page__content" role="tabpanel">
          {activeTab === "vault" && <VaultTab />}
          {activeTab === "ntn" && <NtnTab />}
          {activeTab === "business" && <BusinessTab />}
          {activeTab === "vendor" && <VendorTab />}
        </div>
      </section>
    </ErrorBoundary>
  );
}