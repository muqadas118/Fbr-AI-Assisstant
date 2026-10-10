import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import clsx from "clsx";

import { Spinner } from "./Spinner";
import { Tag } from "./Tag";
import {
  api,
  ApiError,
  type UploadDocumentAnalysisResponse,
  type UploadDocumentVerifyResponse,
  type UploadInvoiceProcessResponse,
  type UploadMeta,
} from "../../lib/api";

export type UploadMode = "verify" | "analyze" | "invoice";

export type UploadOutcomeData =
  | { kind: "verify"; response: UploadDocumentVerifyResponse }
  | { kind: "analyze"; response: UploadDocumentAnalysisResponse }
  | { kind: "invoice"; response: UploadInvoiceProcessResponse };

export interface UploadOutcome {
  mode: UploadMode;
  data: UploadOutcomeData;
}

interface FileDropProps {
  mode: UploadMode;
  label?: string;
  hint?: string;
  /** Only used in invoice mode. */
  invoiceId?: string;
  onOutcome?: (outcome: UploadOutcome) => void;
}

const ACTION_LABEL: Record<UploadMode, string> = {
  verify: "Verify document",
  analyze: "Analyze document",
  invoice: "Process Invoice",
};

export function FileDrop({ mode, label, hint, invoiceId, onOutcome }: FileDropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<UploadMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Partial<Record<UploadMode, UploadOutcomeData>>>({});

  function pick(next: File | null) {
    setFile(next);
    setError(null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files?.[0] ?? null);
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    pick(event.target.files?.[0] ?? null);
  }

  async function run(withMode: UploadMode) {
    if (!file) {
      setError("Select a file first.");
      return;
    }

    setBusy(withMode);
    setError(null);

    try {
      let result: UploadOutcomeData;
      if (withMode === "verify") {
        result = { kind: "verify", response: await api.documents.uploadVerify(file) };
      } else if (withMode === "analyze") {
        result = { kind: "analyze", response: await api.documents.uploadAnalyze(file) };
      } else {
        result = { kind: "invoice", response: await api.invoices.uploadProcess(file, invoiceId) };
      }
      setResults((prev) => ({ ...prev, [withMode]: result }));
      onOutcome?.({ mode: withMode, data: result });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Upload failed. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const modes: UploadMode[] = [mode];

  return (
    <div className="file-drop">
      <div
        className={clsx("field__dropzone", dragging && "field__dropzone--active")}
        role="button"
        tabIndex={0}
        aria-label="Upload a document"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <div className="field__dropzone-icon" aria-hidden>
          <UploadIcon />
        </div>
        <div className="field__dropzone-text">
          <strong>{file ? file.name : (label ?? "Drop a file or click to browse")}</strong>
          <span>{file ? formatBytes(file.size) : (hint ?? "PDF, image, DOCX, XLSX, CSV, TXT — any type up to 15 MB")}</span>
        </div>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          onChange={onChange}
          aria-label="File input"
        />
      </div>

      <div className="file-drop__actions">
        {modes.map((item) => (
          <button
            key={item}
            type="button"
            className={clsx("btn", item === mode ? "btn--primary" : "btn--ghost", "btn--sm")}
            disabled={busy !== null || !file}
            onClick={() => void run(item)}
          >
            {busy === item ? <Spinner size="sm" /> : <CheckIcon />}
            {busy === item ? "Working..." : ACTION_LABEL[item]}
          </button>
        ))}
        {file ? (
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => pick(null)}>
            Clear
          </button>
        ) : null}
      </div>

      {error ? <p className="field__error" role="alert">{error}</p> : null}

      {modes.map((item) => (
        <ResultPanel key={item} mode={item} result={results[item]} />
      ))}
    </div>
  );
}

function ResultPanel({ mode, result }: { mode: UploadMode; result?: UploadOutcomeData }) {
  if (!result) return null;

  const rows = rowsFor(result);
  const failed =
    result.kind === "verify" &&
    (result.response.ntn_format_valid === false || result.response.cnic_format_valid === false);

  return (
    <div className={clsx("upload-report", failed && "upload-report--warn")}>
      <div className="upload-report__head">
        <span className="upload-report__title">
          {mode === "verify" ? "Verification result" : mode === "analyze" ? "Analysis result" : "Invoice result"}
        </span>
        {failed ? <Tag variant="err">Check the flagged fields</Tag> : null}
      </div>
      <ul className="upload-report__rows">
        {rows.map((row) => (
          <li key={row.key} className="upload-report__row">
            <span className="upload-report__label">{row.label}</span>
            <span className="upload-report__value">{row.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface Row {
  key: string;
  label: string;
  value: string;
}

const LABEL_OVERRIDES: Record<string, string> = {
  id: "Invoice ID",
  person_name: "Person name",
  person_cnic: "Person CNIC",
  person_ntn: "Person NTN",
  company_name: "Company",
  company_ntn: "Company NTN",
  reference_number: "Reference #",
  issue_date: "Issue date",
  net_amount: "Net amount",
  tax_rate: "Tax rate",
  tax_section: "Tax section",
  fbr_reference: "FBR reference",
  address: "Address",
  overall_quality_score: "Quality score",
  duration_ms: "Duration (ms)",
  is_valid: "Valid",
  is_duplicate: "Duplicate",
  itc_eligible: "ITC eligible",
  tax_impact: "Tax impact",
  ntn_format_valid: "NTN format valid",
  cnic_format_valid: "CNIC format valid",
  ntn: "NTN",
  cnic: "CNIC",
  ntn_s: "NTN",
  confidence: "Confidence",
  extraction_quality: "Extraction quality",
  document_type: "Document type",
  document_category: "Document category",
  classification_confidence: "Classification confidence",
  is_scanned: "Scanned / OCR",
  text_length: "Characters read",
  page_count: "Pages",
  total_amount: "Total amount",
  tax_amount: "Tax amount",
  tax_percentage: "Tax rate",
  subtotal: "Subtotal",
  currency: "Currency",
  vendor_name: "Vendor",
  vendor_ntn: "Vendor NTN",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  invoice_id: "Invoice id",
  invoice_status: "Invoice status",
  invoice_amount: "Invoice amount",
  tax_credit_eligible: "Tax credit eligible",
  disallowed: "Disallowed",
};

const SKIP_KEYS = new Set([
  "meta", // already rendered as a summary block via metaRows()
  "analysis_id",
  "timestamp",
  "matched_signals",
  "matched_tokens",
  "raw",
  "warnings",
  "ocr_simulated", // covered by the OCR summary row
  "raw_text", // full document text — not useful as a report row
]);

function rowsFor(result: UploadOutcomeData): Row[] {
  if (result.kind === "verify") {
    return [
      ...metaRows(result.response.meta),
      ...flattenRows(result.response as unknown as Record<string, unknown>),
    ];
  }
  if (result.kind === "analyze") {
    const { formatted_text: _formattedText, ...analysis } = result.response.analysis;
    return [
      ...metaRows(result.response.meta),
      ...flattenRows(analysis as Record<string, unknown>),
    ];
  }
  return [
    ...metaRows(result.response.meta),
    ...flattenRows(result.response.result as unknown as Record<string, unknown>),
  ];
}

function metaRows(meta: UploadMeta): Row[] {
  const rows: Row[] = [
    { key: "meta.filename", label: "File", value: `${meta.filename} · ${formatBytes(meta.size_bytes)}` },
  ];
  if (meta.pages) rows.push({ key: "meta.pages", label: "Pages", value: String(meta.pages) });
  rows.push({ key: "meta.ocr", label: "OCR", value: meta.ocr_simulated ? "Simulated" : "Not needed" });
  if (meta.ocr_warning) rows.push({ key: "meta.ocr_warning", label: "OCR note", value: meta.ocr_warning });
  return rows;
}

function flattenRows(data: Record<string, unknown>, parent = ""): Row[] {
  const rows: Row[] = [];

  for (const [key, value] of Object.entries(data)) {
    if (SKIP_KEYS.has(key)) continue;
    const keyPath = parent ? `${parent}.${key}` : key;

    if (value && typeof value === "object" && !Array.isArray(value)) {
      rows.push(...flattenRows(value as Record<string, unknown>, keyPath));
      continue;
    }

    const rendered = renderValue(value);
    if (rendered === null) continue;
    rows.push({ key: keyPath, label: LABEL_OVERRIDES[key] ?? humanize(key), value: rendered });
  }

  return rows;
}

function renderValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return value
      .slice(0, 4)
      .map((item) => {
        if (item && typeof item === "object") {
          const parts = ["code", "field", "issue", "message", "description", "severity"]
            .filter((k) => {
              const v = (item as Record<string, unknown>)[k];
              return v !== null && v !== undefined && v !== "";
            })
            .map((k) => String((item as Record<string, unknown>)[k]));
          return parts.length > 0 ? parts.join(": ") : "";
        }
        return String(item);
      })
      .filter((s) => s !== "")
      .join("; ") || null;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return null;
    return entries.map(([k, v]) => `${humanize(k)}: ${renderValue(v) ?? "-"}`).join(" · ");
  }
  const text = String(value);
  return text.length > 160 ? `${text.slice(0, 160)}…` : text;
}

function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

interface FileChipProps {
  file: File;
  onRemove?: () => void;
}

/** Small read-only chip for files attached to a form (e.g. an invoice). */
export function FileChip({ file, onRemove }: FileChipProps) {
  return (
    <div className="file-chip" title={`${file.name} · ${formatBytes(file.size)}`}>
      <span className="file-chip__name">{file.name}</span>
      <span className="file-chip__size">{formatBytes(file.size)}</span>
      {onRemove ? (
        <button type="button" className="file-chip__remove" onClick={onRemove} aria-label={`Remove ${file.name}`}>
          ×
        </button>
      ) : null}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3 3 7v6c0 4.5 3.6 7.6 9 8 5.4-.4 9-3.5 9-8V7z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}
