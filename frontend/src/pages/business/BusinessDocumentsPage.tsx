import { useState, useCallback, useEffect } from "react";
import clsx from "clsx";
import {
  api,
  ApiError,
  NetworkError,
  type DocumentAnalysisResponse,
  type DocumentVerifyResponse,
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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AnalyzedDoc {
  id: string;
  analysis_id: string;
  timestamp: string;
  document_type: string;
  document_category: string;
  classification_confidence: number;
  extracted_info: DocumentAnalysisResponse["extracted_info"];
  parsed_form?: DocumentAnalysisResponse["parsed_form"];
  filename?: string;
}

interface VerifiedIdentity {
  id: string;
  timestamp: string;
  ntn?: string;
  cnic?: string;
  name?: string;
  confidence: number;
}

interface SupportedDocType {
  type: string;
  category: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPkr(value: number | undefined | null): string {
  if (value == null) return "—";
  return `PKR ${value.toLocaleString("en-US")}`;
}

function confidenceVariant(confidence: number): "ok" | "warn" | "err" {
  if (confidence >= 0.8) return "ok";
  if (confidence >= 0.5) return "warn";
  return "err";
}

function confidenceLabel(confidence: number): string {
  return `${Math.round(confidence * 100)}% confidence`;
}

function ExtractionQualityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.8 ? "var(--c-ok)" : score >= 0.5 ? "var(--c-warn)" : "var(--c-err)";
  return (
    <div className="doc-quality">
      <div className="health-progress__track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="health-progress__fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="doc-quality__label" style={{ color }}>{pct}% extraction quality</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 1: Analyze Business Document
// ---------------------------------------------------------------------------

function AnalyzeSection({
  onAnalyze,
}: {
  onAnalyze: (doc: AnalyzedDoc) => void;
}) {
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [typeHint, setTypeHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<DocumentAnalysisResponse | null>(null);

  const { show: notify } = useNotification();

  const submit = useCallback(async () => {
    if (!text.trim()) return;
    setError(null);
    setPreview(null);
    setLoading(true);
    try {
      const resp = await api.documents.analyze(
        text.trim(),
        filename.trim() || undefined,
        typeHint.trim() || undefined,
      );
      setPreview(resp);
      const doc: AnalyzedDoc = {
        id: `doc-${Date.now()}`,
        analysis_id: resp.analysis_id,
        timestamp: resp.timestamp,
        document_type: resp.document_type,
        document_category: resp.document_category,
        classification_confidence: resp.classification_confidence,
        extracted_info: resp.extracted_info,
        parsed_form: resp.parsed_form,
        filename: filename.trim() || undefined,
      };
      onAnalyze(doc);
      notify("ok", `Document analyzed: ${resp.document_type}`);
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }, [text, filename, typeHint, notify, onAnalyze]);

  return (
    <Card title="Analyze Business Document" subtitle="Paste sales tax invoice or business document text to extract structured data" testId="biz-doc-analyze-card">
      <form
        className="doc-form"
        onSubmit={(e) => { e.preventDefault(); void submit(); }}
        data-testid="biz-doc-analyze-form"
      >
        <Field label="Document Text" data-testid="biz-doc-text" error={!text.trim() && error ? "Document text is required" : undefined}>
          <textarea
            rows={6}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste the full text of your business document here (Sales tax invoice, Form 16A, Withholding statement, FBR sales tax notice, etc.)"
            className="doc-form__textarea"
            data-testid="biz-doc-text-input"
          />
        </Field>
        <div className="grid grid--2">
          <Field label="Filename (optional)" data-testid="biz-doc-filename">
            <input
              type="text"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              placeholder="e.g. vendor_form_16a_2024.pdf"
              data-testid="biz-doc-filename-input"
            />
          </Field>
          <Field label="Document Type Hint (optional)" data-testid="biz-doc-type-hint">
            <input
              type="text"
              value={typeHint}
              onChange={(e) => setTypeHint(e.target.value)}
              placeholder="e.g. Sales Tax Invoice, Form 16A, Withholding Statement"
              data-testid="biz-doc-type-hint-input"
            />
          </Field>
        </div>
        <div className="form__actions">
          <Button
            type="submit"
            variant="primary"
            loading={loading}
            disabled={!text.trim() || loading}
            data-testid="biz-doc-analyze-submit"
          >
            {loading ? "Analyzing…" : "Analyze Document"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => { setText(""); setFilename(""); setTypeHint(""); setPreview(null); setError(null); }}
            data-testid="biz-doc-analyze-reset"
          >
            Clear
          </Button>
        </div>
      </form>

      {loading ? <Loading label="Extracting document data…" testId="biz-doc-analyze-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Analysis failed" description={error} testId="biz-doc-analyze-error" />
      ) : null}

      {preview && !loading ? (
        <div className="doc-result" data-testid="biz-doc-analyze-result">
          <div className="doc-result__header">
            <Tag variant="accent">{preview.document_type}</Tag>
            <Tag variant="default">{preview.document_category}</Tag>
            <Tag variant={confidenceVariant(preview.classification_confidence)}>
              {confidenceLabel(preview.classification_confidence)}
            </Tag>
          </div>

          <Kv
            rows={[
              { key: "Document Type", value: preview.document_type },
              { key: "Category", value: preview.document_category },
              { key: "Classification Confidence", value: (
                <Tag variant={confidenceVariant(preview.classification_confidence)}>
                  {confidenceLabel(preview.classification_confidence)}
                </Tag>
              )},
              { key: "Analysis ID", value: <span className="mono">{preview.analysis_id.slice(0, 20)}…</span> },
              { key: "Duration", value: `${preview.duration_ms}ms` },
            ]}
            testId="biz-doc-classification"
          />

          <hr className="divider" />

          <h4 className="card__title" style={{ fontSize: "14px", marginBottom: "var(--s-3)" }}>Extracted Information</h4>
          <ExtractionQualityBar score={preview.extracted_info.extraction_quality} />
          <Kv
            rows={[
              { key: "Contact Name", value: preview.extracted_info.person_name || "—" },
              { key: "Contact CNIC", value: preview.extracted_info.person_cnic || "—" },
              { key: "Company NTN", value: preview.extracted_info.company_ntn || preview.extracted_info.person_ntn || "—" },
              { key: "Company Name", value: preview.extracted_info.company_name || "—" },
              { key: "Sales Tax Registration No", value: preview.extracted_info.fbr_reference || "—" },
              { key: "Reference Number", value: preview.extracted_info.reference_number || "—" },
              { key: "Issue Date", value: preview.extracted_info.issue_date || "—" },
              { key: "Total Amount", value: formatPkr(preview.extracted_info.total_amount) },
              { key: "Net Amount", value: formatPkr(preview.extracted_info.net_amount) },
              { key: "Currency", value: preview.extracted_info.currency || "PKR" },
              { key: "Tax Rate", value: preview.extracted_info.tax_rate != null ? `${(preview.extracted_info.tax_rate * 100).toFixed(1)}%` : "—" },
              { key: "Tax Amount", value: formatPkr(preview.extracted_info.tax_amount) },
              { key: "Tax Section", value: preview.extracted_info.tax_section || "—" },
              { key: "FBR Reference", value: preview.extracted_info.fbr_reference || "—" },
              { key: "Address", value: preview.extracted_info.address || "—" },
            ]}
            testId="biz-doc-extracted-info"
          />

          {preview.parsed_form ? (
            <>
              <hr className="divider" />
              <h4 className="card__title" style={{ fontSize: "14px", marginBottom: "var(--s-3)" }}>
                Parsed Form — {preview.parsed_form.form_type}
              </h4>
              <p className="small muted" style={{ marginBottom: "var(--s-3)" }}>
                Extracted {preview.parsed_form.fields_extracted}/{preview.parsed_form.total_fields} fields
                ({Math.round(preview.parsed_form.extraction_rate * 100)}% rate)
              </p>
              <Kv
                rows={[
                  { key: "Form Type", value: preview.parsed_form.form_type },
                  { key: "Form Number", value: preview.parsed_form.form_number || "—" },
                  { key: "Tax Year", value: preview.parsed_form.tax_year || "—" },
                  ...(preview.parsed_form.notes.length > 0 ? [{ key: "Notes", value: preview.parsed_form.notes.join("; ") }] : []),
                ]}
                testId="biz-doc-parsed-form"
              />
            </>
          ) : null}

          {preview.summary ? (
            <>
              <hr className="divider" />
              <h4 className="card__title" style={{ fontSize: "14px", marginBottom: "var(--s-3)" }}>Summary</h4>
              <p className="card__body-text">{preview.summary}</p>
            </>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section 2: Verify Business Identity
// ---------------------------------------------------------------------------

function VerifySection({
  onVerify,
}: {
  onVerify: (result: VerifiedIdentity) => void;
}) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<DocumentVerifyResponse | null>(null);

  const { show: notify } = useNotification();

  const submit = useCallback(async () => {
    if (!text.trim()) return;
    setError(null);
    setPreview(null);
    setLoading(true);
    try {
      const resp = await api.documents.verify(text.trim());
      setPreview(resp);
      const item: VerifiedIdentity = {
        id: `verify-${Date.now()}`,
        timestamp: new Date().toISOString(),
        ntn: resp.ntn,
        cnic: resp.cnic,
        name: resp.name,
        confidence: resp.confidence,
      };
      onVerify(item);
      notify("ok", `Identity verified: ${resp.name || resp.ntn || resp.cnic || "document"}`);
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  }, [text, notify, onVerify]);

  return (
    <Card title="Verify Business Identity" subtitle="Extract and verify company NTN / CNIC from business document text" testId="biz-doc-verify-card">
      <form
        className="doc-form"
        onSubmit={(e) => { e.preventDefault(); void submit(); }}
        data-testid="biz-doc-verify-form"
      >
        <Field label="Document Text" data-testid="biz-doc-verify-text">
          <textarea
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste text containing company NTN and/or CNIC numbers for verification (e.g. a sales tax invoice or withholding statement)"
            className="doc-form__textarea"
            data-testid="biz-doc-verify-text-input"
          />
        </Field>
        <div className="form__actions">
          <Button
            type="submit"
            variant="primary"
            loading={loading}
            disabled={!text.trim() || loading}
            data-testid="biz-doc-verify-submit"
          >
            {loading ? "Verifying…" : "Verify Identity"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => { setText(""); setPreview(null); setError(null); }}
            data-testid="biz-doc-verify-reset"
          >
            Clear
          </Button>
        </div>
      </form>

      {loading ? <Loading label="Extracting identity data…" testId="biz-doc-verify-loading" /> : null}

      {error ? (
        <StatusBanner kind="err" title="Verification failed" description={error} testId="biz-doc-verify-error" />
      ) : null}

      {preview && !loading ? (
        <div className="doc-result" data-testid="biz-doc-verify-result">
          <div className="doc-result__header">
            <Tag variant={confidenceVariant(preview.confidence)}>
              {confidenceLabel(preview.confidence)}
            </Tag>
          </div>
          <Kv
            rows={[
              { key: "Name", value: preview.name || "—" },
              { key: "NTN", value: preview.ntn || "—" },
              { key: "CNIC", value: preview.cnic || "—" },
              { key: "Confidence", value: (
                <Tag variant={confidenceVariant(preview.confidence)}>
                  {confidenceLabel(preview.confidence)}
                </Tag>
              )},
              { key: "Extraction Quality", value: (
                <Tag variant={confidenceVariant(preview.extraction_quality)}>
                  {confidenceLabel(preview.extraction_quality)}
                </Tag>
              )},
            ]}
            testId="biz-doc-verify-result-kv"
          />
        </div>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section 3: Supported Business Document Types
// ---------------------------------------------------------------------------

function SupportedTypesSection() {
  const [loading, setLoading] = useState(false);
  const [types, setTypes] = useState<SupportedDocType[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    api.documents.getTypes()
      .then((resp) => {
        if (!mounted) return;
        const items: SupportedDocType[] = (resp.document_types || []).map((t) => ({
          type: t,
          category: resp.categories?.includes(t) ? t : "General",
        }));
        setTypes(items);
      })
      .catch((err) => {
        if (!mounted) return;
        if (err instanceof ApiError || err instanceof NetworkError) {
          setError(err.message);
        } else {
          setError("Could not load supported document types.");
        }
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  if (loading) return <Loading label="Loading supported document types…" testId="biz-doc-types-loading" />;
  if (error) return <StatusBanner kind="err" title="Could not load document types" description={error} testId="biz-doc-types-error" />;

  return (
    <Card
      title="Supported Business Document Types"
      subtitle={`${types.length} recognized business document type${types.length !== 1 ? "s" : ""}`}
      testId="biz-doc-types-card"
    >
      {types.length === 0 ? (
        <p className="card__body-text muted">No business document types available.</p>
      ) : (
        <div className="doc-types-grid" data-testid="biz-doc-types-grid">
          {types.map((dt) => (
            <div key={dt.type} className="doc-type-chip">
              <Tag variant="accent">{dt.type}</Tag>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section 4: Business Analysis History
// ---------------------------------------------------------------------------

function HistorySection({
  analyzedDocs,
  verifiedIdentities,
}: {
  analyzedDocs: AnalyzedDoc[];
  verifiedIdentities: VerifiedIdentity[];
}) {
  const allItems = [
    ...analyzedDocs.map((d) => ({ type: "analysis" as const, item: d, ts: d.timestamp })),
    ...verifiedIdentities.map((v) => ({ type: "verify" as const, item: v, ts: v.timestamp })),
  ].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());

  if (allItems.length === 0) return null;

  return (
    <Card title="Business Analysis History" subtitle={`${allItems.length} item${allItems.length !== 1 ? "s" : ""} in this session`} testId="biz-doc-history-card">
      <div className="doc-history" data-testid="biz-doc-history-list">
        {allItems.map((entry) => (
          <div key={entry.item.id} className={clsx("doc-history__item", `doc-history__item--${entry.type}`)}>
            <div className="doc-history__meta">
              <Tag variant={entry.type === "analysis" ? "accent" : "default"}>
                {entry.type === "analysis" ? "Document" : "Identity"}
              </Tag>
              <span className="small muted">
                {new Date(entry.ts).toLocaleString()}
              </span>
            </div>
            {entry.type === "analysis" ? (
              <div className="doc-history__content">
                <span className="doc-history__title">
                  {(entry.item as AnalyzedDoc).filename || (entry.item as AnalyzedDoc).document_type}
                </span>
                <Tag variant={confidenceVariant((entry.item as AnalyzedDoc).classification_confidence)}>
                  {confidenceLabel((entry.item as AnalyzedDoc).classification_confidence)}
                </Tag>
              </div>
            ) : (
              <div className="doc-history__content">
                <span className="doc-history__title">
                  {(entry.item as VerifiedIdentity).name || (entry.item as VerifiedIdentity).ntn || (entry.item as VerifiedIdentity).cnic || "Verified"}
                </span>
                {(entry.item as VerifiedIdentity).ntn && <span className="mono small">NTN: {(entry.item as VerifiedIdentity).ntn}</span>}
                {(entry.item as VerifiedIdentity).cnic && <span className="mono small">CNIC: {(entry.item as VerifiedIdentity).cnic}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export function BusinessDocumentsPage() {
  const [analyzedDocs, setAnalyzedDocs] = useState<AnalyzedDoc[]>([]);
  const [verifiedIdentities, setVerifiedIdentities] = useState<VerifiedIdentity[]>([]);

  const handleAnalyze = useCallback((doc: AnalyzedDoc) => {
    setAnalyzedDocs((prev) => [doc, ...prev]);
  }, []);

  const handleVerify = useCallback((result: VerifiedIdentity) => {
    setVerifiedIdentities((prev) => [result, ...prev]);
  }, []);

  return (
    <ErrorBoundary>
      <section className="page page--documents">
        <header className="page__header">
          <div>
            <h2 className="page__title">Business Documents</h2>
            <p className="page__subtitle">
              Analyze business documents to extract structured data — sales tax invoices, withholding statements, vendor Form 16A, and company NTN records
            </p>
          </div>
        </header>

        <div className="page__content">
          <AnalyzeSection onAnalyze={handleAnalyze} />
          <VerifySection onVerify={handleVerify} />
          <SupportedTypesSection />
          <HistorySection analyzedDocs={analyzedDocs} verifiedIdentities={verifiedIdentities} />
        </div>
      </section>
    </ErrorBoundary>
  );
}