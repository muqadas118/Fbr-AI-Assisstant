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

type Tab = "vault" | "ntn" | "cnic" | "vendor";

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
// Tab 1: My Vault
// ---------------------------------------------------------------------------

function VaultTab() {
  const [files, setFiles] = useState<VaultFile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newFilename, setNewFilename] = useState("");
  const [newType, setNewType] = useState("Tax Return");
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
    setNewType("Tax Return");
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
        <Button variant="primary" size="sm" onClick={() => setShowAdd(true)} data-testid="vault-add-btn">
          + Add Document
        </Button>
        <span className="small muted">{files.length} document{files.length !== 1 ? "s" : ""} in vault</span>
      </div>

      {showAdd && (
        <Card title="Add Document to Vault" testId="vault-add-card">
          <form
            className="vault-add-form"
            onSubmit={(e) => { e.preventDefault(); void handleAdd(); }}
            data-testid="vault-add-form"
          >
            <div className="grid grid--2">
              <Field label="Filename" data-testid="vault-add-filename">
                <input
                  type="text"
                  value={newFilename}
                  onChange={(e) => setNewFilename(e.target.value)}
                  placeholder="e.g. ITR_2024.pdf"
                  required
                  data-testid="vault-add-filename-input"
                />
              </Field>
              <Field label="Document Type" data-testid="vault-add-type">
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  data-testid="vault-add-type-select"
                >
                  <option>Tax Return</option>
                  <option>WHT Certificate</option>
                  <option>Sales Tax Return</option>
                  <option>Form 16A</option>
                  <option>Salary Certificate</option>
                  <option>Bank Statement</option>
                  <option>Contract</option>
                  <option>Invoice</option>
                  <option>Other</option>
                </select>
              </Field>
            </div>
            <Field label="Content / Notes" data-testid="vault-add-content">
              <textarea
                rows={4}
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="Optional notes or summary of the document…"
                data-testid="vault-add-content-input"
              />
            </Field>
            <div className="form__actions">
              <Button type="submit" variant="primary" data-testid="vault-add-submit">
                Add to Vault
              </Button>
              <Button type="button" variant="ghost" onClick={() => setShowAdd(false)} data-testid="vault-add-cancel">
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {files.length === 0 && !showAdd ? (
        <StatusBanner
          kind="info"
          title="Vault is empty"
          description="Add your first document to the secure vault above."
          testId="vault-empty"
        />
      ) : (
        <div className="vault-table-wrap">
          <table className="vault-table" data-testid="vault-table">
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
                  data-testid={`vault-row-${f.id}`}
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
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setSelectedId(f.id); }} data-testid={`vault-view-${f.id}`}>
                        View
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleDelete(f.id); }} data-testid={`vault-delete-${f.id}`}>
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
        <Card title={`Document: ${selected.filename}`} testId="vault-detail-card">
          <Kv
            rows={[
              { key: "Filename", value: selected.filename },
              { key: "Type", value: <Tag variant="default">{selected.type}</Tag> },
              { key: "Size", value: selected.size },
              { key: "Date Added", value: formatDate(selected.date) },
              { key: "Secure Storage", value: boolTag(selected.secure) },
            ]}
            testId="vault-detail-kv"
          />
          <div className="form__actions" style={{ marginTop: "var(--s-4)" }}>
            <Button variant="ghost" size="sm" onClick={() => setSelectedId(null)} data-testid="vault-detail-close">
              Close
            </Button>
            <Button variant="danger" size="sm" onClick={() => { handleDelete(selected.id); }} data-testid="vault-detail-delete">
              Delete
            </Button>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: Verify NTN
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
      setNtnError("NTN is required");
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
        notify("ok", `NTN ${ntn} verified successfully.`);
      } else {
        notify("warn", `NTN ${ntn} could not be verified.`);
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
      <Card title="Verify NTN" subtitle="Check if a Taxpayer Identification Number is registered with FBR" testId="ntn-verify-card">
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="ntn-verify-form"
        >
          <Field label="NTN" error={ntnError ?? undefined} data-testid="ntn-input-field">
            <input
              type="text"
              value={ntn}
              onChange={(e) => { setNtn(e.target.value); setNtnError(null); }}
              placeholder="e.g. 1234567-9"
              data-testid="ntn-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="ntn-verify-submit">
              {loading ? "Verifying…" : "Verify NTN"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setNtn(""); setResult(null); setError(null); setNtnError(null); }} data-testid="ntn-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying NTN with FBR…" testId="ntn-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="NTN verification failed" description={error} testId="ntn-error" />
      ) : null}

      {result && !loading ? (
        <Card title="Verification Result" testId="ntn-result-card">
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
            testId="ntn-result-kv"
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: Verify CNIC
// ---------------------------------------------------------------------------

function CnicTab() {
  const [cnic, setCnic] = useState(() => useProfile.getState().cnic || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [cnicError, setCnicError] = useState<string | null>(null);

  const { show: notify } = useNotification();

  const validate = (): boolean => {
    const cleaned = cnic.replace(/\D/g, "");
    if (!cnic.trim() || cleaned.length < 10) {
      setCnicError("Enter a valid CNIC (e.g. 1234567890123)");
      return false;
    }
    setCnicError(null);
    return true;
  };

  const submit = useCallback(async () => {
    if (!validate()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const resp = await api.verify.cnic(cnic.trim());
      setResult(resp);
      useProfile.getState().setCnic(cnic.trim());
      if (resp.is_verified) {
        notify("ok", `CNIC ${cnic} verified.`);
      } else {
        notify("warn", `CNIC ${cnic} could not be verified.`);
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
  }, [cnic, notify]);

  return (
    <div className="vault-tab">
      <Card title="Verify CNIC" subtitle="Check filer status and identity details for a Computerized National Identity Card" testId="cnic-verify-card">
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="cnic-verify-form"
        >
          <Field label="CNIC" error={cnicError ?? undefined} data-testid="cnic-input-field">
            <input
              type="text"
              value={cnic}
              onChange={(e) => { setCnic(e.target.value); setCnicError(null); }}
              placeholder="e.g. 1234567890123"
              data-testid="cnic-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="cnic-verify-submit">
              {loading ? "Verifying…" : "Verify CNIC"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setCnic(""); setResult(null); setError(null); setCnicError(null); }} data-testid="cnic-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying CNIC with FBR…" testId="cnic-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="CNIC verification failed" description={error} testId="cnic-error" />
      ) : null}

      {result && !loading ? (
        <Card title="Verification Result" testId="cnic-result-card">
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
            testId="cnic-result-kv"
          />
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: Verify Vendor
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
      setVendorError("Vendor NTN is required");
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
  }, [vendorNtn, notify]);

  const details = result?.details as Record<string, unknown> | undefined;

  return (
    <div className="vault-tab">
      <Card title="Verify Vendor" subtitle="Check if a vendor is registered with FBR, their filer status, and WHT compliance" testId="vendor-verify-card">
        <form
          className="vault-verify-form"
          onSubmit={(e) => { e.preventDefault(); void submit(); }}
          data-testid="vendor-verify-form"
        >
          <Field label="Vendor NTN" error={vendorError ?? undefined} data-testid="vendor-input-field">
            <input
              type="text"
              value={vendorNtn}
              onChange={(e) => { setVendorNtn(e.target.value); setVendorError(null); }}
              placeholder="e.g. 1234567-9"
              data-testid="vendor-verify-input"
            />
          </Field>
          <div className="form__actions">
            <Button type="submit" variant="primary" loading={loading} disabled={loading} data-testid="vendor-verify-submit">
              {loading ? "Verifying…" : "Verify Vendor"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => { setVendorNtn(""); setResult(null); setError(null); setVendorError(null); }} data-testid="vendor-verify-reset">
              Clear
            </Button>
          </div>
        </form>
      </Card>

      {loading ? <Loading label="Verifying vendor with FBR…" testId="vendor-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Vendor verification failed" description={error} testId="vendor-error" />
      ) : null}

      {result && !loading ? (
        <>
          <Card title="Verification Result" testId="vendor-result-card">
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
              testId="vendor-result-kv"
            />
            {details?.warnings && Array.isArray(details.warnings) && (details.warnings as string[]).length > 0 ? (
              <>
                <hr className="divider" />
                <h4 style={{ fontSize: "14px", marginBottom: "var(--s-2)" }}>Warnings</h4>
                {(details.warnings as string[]).map((w, i) => (
                  <StatusBanner key={i} kind="warn" title={w} testId={`vendor-warning-${i}`} />
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

export function VaultPage() {
  const [activeTab, setActiveTab] = useState<Tab>("vault");

  const tabs: { id: Tab; label: string }[] = [
    { id: "vault", label: "My Vault" },
    { id: "ntn", label: "Verify NTN" },
    { id: "cnic", label: "Verify CNIC" },
    { id: "vendor", label: "Verify Vendor" },
  ];

  return (
    <ErrorBoundary>
      <section className="page page--vault">
        <header className="page__header">
          <div>
            <h2 className="page__title">Tax Vault</h2>
            <p className="page__subtitle">
              Secure document storage and FBR verification tools — NTN, CNIC, and vendor checks.
            </p>
          </div>
        </header>

        <div className="page__tabs" role="tablist" data-testid="vault-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={clsx("tab-btn", activeTab === tab.id && "tab-btn--active")}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`vault-tab-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="page__content" role="tabpanel">
          {activeTab === "vault" && <VaultTab />}
          {activeTab === "ntn" && <NtnTab />}
          {activeTab === "cnic" && <CnicTab />}
          {activeTab === "vendor" && <VendorTab />}
        </div>
      </section>
    </ErrorBoundary>
  );
}
