import { useState, useCallback, useEffect } from "react";
import clsx from "clsx";
import {
  api,
  ApiError,
  NetworkError,
  type VaultDocument,
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
// Helpers
// ---------------------------------------------------------------------------

const DOC_TYPES = [
  "Tax Return",
  "WHT Certificate",
  "Sales Tax Return",
  "Form 16A",
  "Salary Certificate",
  "Bank Statement",
  "Contract",
  "Invoice",
  "Other",
];

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

// ---------------------------------------------------------------------------
// Vault Page — persistent per-user document storage, backed by the live
// /vault/documents API (SQLite). Verification lives in the
// Verification Center (/personal/verification) — see VerificationPage.tsx.
// ---------------------------------------------------------------------------

export function VaultPage() {
  const { show: notify } = useNotification();
  const [docs, setDocs] = useState<VaultDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newFilename, setNewFilename] = useState("");
  const [newType, setNewType] = useState("Tax Return");
  const [newContent, setNewContent] = useState("");

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const resp = await api.vault.list();
      setDocs(resp.documents);
    } catch (err) {
      if (err instanceof ApiError) setLoadError(`API error (${err.status}): ${err.detail}`);
      else if (err instanceof NetworkError) setLoadError("Network error — could not reach the server.");
      else setLoadError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchDocs();
  }, [fetchDocs]);

  const handleAdd = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFilename.trim()) return;
    setSaving(true);
    try {
      const doc = await api.vault.create({
        filename: newFilename.trim(),
        doc_type: newType,
        content: newContent,
      });
      setDocs((prev) => [doc, ...prev]);
      setNewFilename("");
      setNewType("Tax Return");
      setNewContent("");
      setShowAdd(false);
      notify("ok", `“${doc.filename}” added to vault.`);
    } catch (err) {
      if (err instanceof ApiError) notify("err", `Failed to add document: ${err.detail}`);
      else if (err instanceof NetworkError) notify("err", "Network error — could not reach the server.");
      else notify("err", "An unexpected error occurred.");
    } finally {
      setSaving(false);
    }
  }, [newFilename, newType, newContent, notify]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await api.vault.remove(id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
      if (selectedId === id) setSelectedId(null);
      notify("ok", "Document deleted from vault.");
    } catch (err) {
      if (err instanceof ApiError) notify("err", `Delete failed: ${err.detail}`);
      else notify("err", "An unexpected error occurred.");
    }
  }, [selectedId, notify]);

  const selected = docs.find((d) => d.id === selectedId) ?? null;

  return (
    <ErrorBoundary>
      <section className="page page--vault">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Vault</div>
            <h2 className="page__title">Tax Vault</h2>
            <p className="page__subtitle">
              Secure, persistent document storage for your tax records — returns, certificates, and statements.
            </p>
          </div>
        </header>

        <div className="page__content">
          <div className="vault-toolbar">
            <Button variant="primary" size="sm" onClick={() => setShowAdd((v) => !v)} data-testid="vault-add-btn">
              {showAdd ? "Close Form" : "+ Add Document"}
            </Button>
            <span className="small muted">{docs.length} document{docs.length !== 1 ? "s" : ""} in vault</span>
          </div>

          {loadError ? (
            <StatusBanner kind="err" title="Failed to load vault" description={loadError} testId="vault-load-error" />
          ) : null}

          {showAdd && (
            <Card title="Add Document to Vault" testId="vault-add-card">
              <form
                className="vault-add-form"
                onSubmit={(e) => { void handleAdd(e); }}
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
                    <Select
                      value={newType}
                      onChange={setNewType}
                      testId="vault-add-type-select"
                      ariaLabel="Document type"
                      options={DOC_TYPES}
                    />
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
                  <Button type="submit" variant="primary" loading={saving} disabled={saving} data-testid="vault-add-submit">
                    {saving ? "Saving…" : "Add to Vault"}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setShowAdd(false)} data-testid="vault-add-cancel">
                    Cancel
                  </Button>
                </div>
              </form>
            </Card>
          )}

          {loading ? (
            <div className="vault-tab">
              <Loading label="Loading your vault…" testId="vault-loading" />
            </div>
          ) : !loadError && docs.length === 0 && !showAdd ? (
            <StatusBanner
              kind="info"
              title="Vault is empty"
              description="Add your first document to the secure vault above — it will be saved to your account and survive page refreshes."
              testId="vault-empty"
            />
          ) : docs.length > 0 ? (
            <div className="vault-table-wrap card">
              <table className="vault-table table--fbr" data-testid="vault-table">
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
                  {docs.map((f) => (
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
                          <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); void handleDelete(f.id); }} data-testid={`vault-delete-${f.id}`}>
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

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
              {selected.content ? (
                <>
                  <hr className="divider" />
                  <h4 style={{ fontSize: "14px", margin: "0 0 var(--s-2)" }}>Content / Notes</h4>
                  <p className="card__body-text" style={{ whiteSpace: "pre-wrap", margin: 0 }} data-testid="vault-detail-content">
                    {selected.content}
                  </p>
                </>
              ) : null}
              <div className="form__actions" style={{ marginTop: "var(--s-4)" }}>
                <Button variant="ghost" size="sm" onClick={() => setSelectedId(null)} data-testid="vault-detail-close">
                  Close
                </Button>
                <Button variant="danger" size="sm" onClick={() => { void handleDelete(selected.id); }} data-testid="vault-detail-delete">
                  Delete
                </Button>
              </div>
            </Card>
          ) : null}

          <StatusBanner
            kind="info"
            title="Persistent vault storage"
            description="Documents are saved to the backend vault database and survive page refreshes. Text storage with per-user scoping — direct PDF file uploads arrive with the next storage phase."
            testId="vault-persistent-note"
          />
        </div>
      </section>
    </ErrorBoundary>
  );
}
