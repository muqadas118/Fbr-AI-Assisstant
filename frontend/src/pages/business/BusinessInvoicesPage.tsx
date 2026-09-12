import { useState, useCallback, useEffect } from "react";
import clsx from "clsx";
import {
  api,
  ApiError,
  NetworkError,
  type InvoiceProcessResponse,
  type InvoiceDashboard,
  type ReconciliationReport,
  type InvoiceIssue,
} from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Loading } from "@/components/shell/Loading";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Field } from "@/components/ui/Field";
import { Kv } from "@/components/ui/Kv";
import { useNotification } from "@/state/notifications";

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDate(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-PK", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatPkr(val: number | undefined): string {
  if (val == null) return "—";
  return `PKR ${val.toLocaleString("en-US")}`;
}

function invoiceTypeVariant(t: string): "accent" | "warn" | "default" {
  switch (t.toLowerCase()) {
    case "sales": return "accent";
    case "purchase": return "warn";
    default: return "default";
  }
}

// ─── Invoice Issues ─────────────────────────────────────────────────────────

function InvoiceIssuesView({ issues }: { issues: InvoiceIssue[] }) {
  if (issues.length === 0) {
    return (
      <div className="inv-issues-empty" data-testid="biz-issues-empty">
        <Tag variant="ok">No issues found</Tag>
      </div>
    );
  }

  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  const infos = issues.filter((i) => i.severity === "info");

  return (
    <div className="inv-issues" data-testid="biz-issues">
      {errors.length > 0 && (
        <div className="inv-issues__group">
          <div className="inv-issues__group-head">
            <Tag variant="err">{errors.length} Error{errors.length !== 1 ? "s" : ""}</Tag>
          </div>
          <ul className="inv-issues__list">
            {errors.map((issue, i) => (
              <li key={i} className="inv-issues__item inv-issues__item--error" data-testid={`biz-issue-error-${i}`}>
                <span className="inv-issues__field">{issue.field}</span>
                <span className="inv-issues__message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="inv-issues__group">
          <div className="inv-issues__group-head">
            <Tag variant="warn">{warnings.length} Warning{warnings.length !== 1 ? "s" : ""}</Tag>
          </div>
          <ul className="inv-issues__list">
            {warnings.map((issue, i) => (
              <li key={i} className="inv-issues__item inv-issues__item--warning" data-testid={`biz-issue-warning-${i}`}>
                <span className="inv-issues__field">{issue.field}</span>
                <span className="inv-issues__message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {infos.length > 0 && (
        <div className="inv-issues__group">
          <div className="inv-issues__group-head">
            <Tag variant="accent">{infos.length} Note{infos.length !== 1 ? "s" : ""}</Tag>
          </div>
          <ul className="inv-issues__list">
            {infos.map((issue, i) => (
              <li key={i} className="inv-issues__item inv-issues__item--info" data-testid={`biz-issue-info-${i}`}>
                <span className="inv-issues__field">{issue.field}</span>
                <span className="inv-issues__message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Process Result ─────────────────────────────────────────────────────────

function ProcessResultView({ result }: { result: InvoiceProcessResponse }) {
  return (
    <div className="inv-result" data-testid="biz-result">
      {/* Status banner */}
      <div className="inv-result__status">
        {result.validation.is_valid ? (
          <StatusBanner
            kind="ok"
            title="Business invoice is valid"
            description={`Validation score: ${result.validation.score}/100. The sales or purchase invoice appears correctly formatted for your business sales tax records.`}
            testId="biz-valid-banner"
          />
        ) : (
          <StatusBanner
            kind="err"
            title="Business invoice has validation issues"
            description={`Validation score: ${result.validation.score}/100. Review the issues below before booking input/output tax.`}
            testId="biz-invalid-banner"
          />
        )}
      </div>

      {/* Invoice details */}
      <Card title="Business Invoice Details" testId="biz-details-card">
        <Kv
          rows={[
            result.invoice.number
              ? { key: "Invoice #", value: <span className="mono">{result.invoice.number}</span> }
              : null,
            result.invoice.date
              ? { key: "Date", value: formatDate(result.invoice.date) }
              : null,
            { key: "Type", value: <Tag variant={invoiceTypeVariant(result.invoice.type)}>{result.invoice.type}</Tag> },
            result.invoice.seller_ntn
              ? { key: "Supplier/Vendor NTN", value: <span className="mono">{result.invoice.seller_ntn}</span> }
              : null,
            result.invoice.buyer_ntn
              ? { key: "Buyer NTN", value: <span className="mono">{result.invoice.buyer_ntn}</span> }
              : null,
            {
              key: "Subtotal",
              value: formatPkr(result.invoice.subtotal),
            },
            {
              key: "Tax Rate",
              value: result.invoice.tax_rate != null ? `${(result.invoice.tax_rate * 100).toFixed(1)}%` : "—",
            },
            {
              key: "Sales Tax Amount",
              value: formatPkr(result.invoice.tax_amount),
            },
            {
              key: "Total",
              value: <strong style={{ fontSize: "15px" }}>{formatPkr(result.invoice.total)}</strong>,
            },
          ].filter(Boolean) as Array<{ key: string; value: React.ReactNode }>}
          testId="biz-details-kv"
        />
      </Card>

      {/* Validation */}
      <Card
        title="Validation Results"
        subtitle={`${result.validation.errors} errors, ${result.validation.warnings} warnings`}
        testId="biz-validation-card"
      >
        <div className="inv-validation__score-row">
          <div className="inv-validation__score-label">Validation Score</div>
          <div className="inv-validation__score-bar">
            <div
              className="inv-validation__score-fill"
              style={{
                width: `${result.validation.score}%`,
                background: result.validation.score >= 80
                  ? "var(--c-ok)"
                  : result.validation.score >= 50
                  ? "var(--c-warn)"
                  : "var(--c-err)",
              }}
            />
          </div>
          <div
            className="inv-validation__score-number"
            style={{
              color: result.validation.score >= 80
                ? "var(--c-ok)"
                : result.validation.score >= 50
                ? "var(--c-warn)"
                : "var(--c-err)",
            }}
          >
            {result.validation.score}/100
          </div>
        </div>

        <InvoiceIssuesView issues={result.validation.issues} />
      </Card>

      {/* Duplicate & ITC */}
      <div className="inv-result__badges">
        {result.is_duplicate && (
          <StatusBanner
            kind="warn"
            title={result.duplicate_of ? `Possible duplicate of ${result.duplicate_of}` : "Possible duplicate detected"}
            description="Review this business invoice carefully. A duplicate may inflate your input tax (ITC) claim or sales tax output."
            testId="biz-duplicate-banner"
          />
        )}
        {result.itc_eligible ? (
          <StatusBanner
            kind="ok"
            title="Input Tax (ITC) Eligible"
            description="Input Tax Credit can be claimed on this supplier invoice against your business sales tax output."
            testId="biz-itc-eligible"
          />
        ) : (
          <StatusBanner
            kind="warn"
            title="Input Tax (ITC) Not Eligible"
            description="Input Tax Credit cannot be claimed on this invoice. Common reasons include a missing supplier NTN, invalid invoice number, or non-filer supplier status."
            testId="biz-itc-ineligible"
          />
        )}
        {result.tax_impact !== 0 && (
          <Card title="Tax Impact" testId="biz-tax-impact-card">
            <Kv
              rows={[{
                key: "Net Sales Tax Impact",
                value: (
                  <strong style={{ color: result.tax_impact >= 0 ? "var(--c-err)" : "var(--c-ok)" }}>
                    {result.tax_impact >= 0 ? "Payable to FBR: " : "Creditable: "}
                    {formatPkr(Math.abs(result.tax_impact))}
                  </strong>
                ),
              }]}
              testId="biz-tax-impact-kv"
            />
          </Card>
        )}
      </div>

      {/* Summary */}
      {result.summary && (
        <Card title="Analysis Summary" testId="biz-summary-card">
          <p className="inv-summary__text">{result.summary}</p>
          <p className="inv-summary__meta small muted">
            Processed in {result.duration_ms}ms · ID: {result.analysis_id}
          </p>
        </Card>
      )}
    </div>
  );
}

// ─── Reconciliation ─────────────────────────────────────────────────────────

function ReconcileView() {
  const [salesJson, setSalesJson] = useState("");
  const [purchasesJson, setPurchasesJson] = useState("");
  const [reconciling, setReconciling] = useState(false);
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const { show: notify } = useNotification();

  const runReconcile = useCallback(async () => {
    setJsonError(null);
    setError(null);

    let salesData: Array<Record<string, unknown>> = [];
    let purchaseData: Array<Record<string, unknown>> = [];

    if (salesJson.trim()) {
      try {
        salesData = JSON.parse(salesJson);
        if (!Array.isArray(salesData)) throw new Error("Sales invoices must be a JSON array.");
      } catch {
        setJsonError("Sales JSON is invalid. Please enter a valid JSON array.");
        return;
      }
    }

    if (purchasesJson.trim()) {
      try {
        purchaseData = JSON.parse(purchasesJson);
        if (!Array.isArray(purchaseData)) throw new Error("Purchase invoices must be a JSON array.");
      } catch {
        setJsonError("Purchase JSON is invalid. Please enter a valid JSON array.");
        return;
      }
    }

    if (salesData.length === 0 && purchaseData.length === 0) {
      setJsonError("Please enter at least one sales or purchase invoice.");
      return;
    }

    setReconciling(true);
    try {
      const resp = await api.invoices.reconcile({
        sales_invoices: salesData,
        purchase_invoices: purchaseData,
      });
      setReport(resp);
      notify("ok", "Reconciliation complete.");
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Cannot reach the server.");
        notify("err", "Cannot reach the backend server.");
      } else if (err instanceof ApiError) {
        setError(`Reconciliation failed: ${err.detail}`);
        notify("err", `Reconciliation failed: ${err.detail}`);
      } else {
        setError("An unexpected error occurred.");
        notify("err", "Unexpected error during reconciliation.");
      }
    } finally {
      setReconciling(false);
    }
  }, [salesJson, purchasesJson, notify]);

  const clearReconcile = () => {
    setReport(null);
    setError(null);
    setJsonError(null);
    setSalesJson("");
    setPurchasesJson("");
  };

  return (
    <Card
      title="Sales Tax Period Reconciliation"
      subtitle="Enter your business sales and supplier purchase invoices as JSON arrays to reconcile output tax against input tax for a filing period"
      testId="biz-reconcile-card"
    >
      <div className="inv-reconcile">
        <div className="inv-reconcile__fields">
          <Field
            label="Sales Invoices (JSON array)"
            helperText='e.g. [{"number":"SINV-001","date":"2024-01-15","total":50000,"tax_amount":9000}, …]'
            error={jsonError && jsonError.includes("Sales") ? jsonError : undefined}
            data-testid="biz-sales-field"
          >
            <textarea
              className="inv-reconcile__textarea"
              value={salesJson}
              onChange={(e) => {
                setSalesJson(e.target.value);
                setJsonError(null);
              }}
              placeholder='[{"number":"SINV-001","date":"2024-01-15","total":50000,"tax_amount":9000}, …]'
              rows={5}
              disabled={reconciling}
              data-testid="biz-sales-input"
            />
          </Field>

          <Field
            label="Purchase / Supplier Invoices (JSON array)"
            helperText='e.g. [{"number":"PINV-001","date":"2024-01-10","total":30000,"tax_amount":5400}, …]'
            error={jsonError && jsonError.includes("Purchase") ? jsonError : undefined}
            data-testid="biz-purchases-field"
          >
            <textarea
              className="inv-reconcile__textarea"
              value={purchasesJson}
              onChange={(e) => {
                setPurchasesJson(e.target.value);
                setJsonError(null);
              }}
              placeholder='[{"number":"PINV-001","date":"2024-01-10","total":30000,"tax_amount":5400}, …]'
              rows={5}
              disabled={reconciling}
              data-testid="biz-purchases-input"
            />
          </Field>
        </div>

        {jsonError ? (
          <StatusBanner
            kind="err"
            title="Invalid JSON"
            description={jsonError}
            testId="biz-json-error"
          />
        ) : null}

        {error ? (
          <StatusBanner
            kind="err"
            title="Reconciliation failed"
            description={error}
            testId="biz-reconcile-error"
          />
        ) : null}

        {reconciling ? (
          <Loading label="Reconciling sales tax period…" testId="biz-reconciling" />
        ) : (
          <div className="inv-reconcile__actions">
            <Button
              variant="primary"
              onClick={() => void runReconcile()}
              data-testid="biz-reconcile-button"
            >
              Reconcile Period
            </Button>
            <Button variant="ghost" onClick={clearReconcile} data-testid="biz-reconcile-clear">
              Clear
            </Button>
          </div>
        )}

        {report && !reconciling && (
          <div className="inv-reconcile__report" data-testid="biz-reconcile-report">
            <div className="inv-reconcile__report-head">
              <h4 className="inv-reconcile__report-title">Sales Tax Reconciliation Report</h4>
              <Tag variant={report.confidence_score >= 0.8 ? "ok" : report.confidence_score >= 0.5 ? "warn" : "err"}>
                {Math.round(report.confidence_score * 100)}% confidence
              </Tag>
            </div>

            <Kv
              rows={[
                { key: "Total Invoices", value: String(report.total_invoices) },
                { key: "Total Sales", value: formatPkr(report.total_sales) },
                { key: "Total Purchases", value: formatPkr(report.total_purchases) },
                { key: "Output Tax (Sales)", value: formatPkr(report.total_output_tax) },
                { key: "Input Tax (Purchases)", value: formatPkr(report.total_input_tax) },
                {
                  key: "Net Payable / Credit",
                  value: (
                    <strong style={{ color: report.net_payable >= 0 ? "var(--c-err)" : "var(--c-ok)" }}>
                      {report.net_payable >= 0 ? "Payable: " : "Credit: "}
                      {formatPkr(Math.abs(report.net_payable))}
                    </strong>
                  ),
                },
                { key: "Vendor / Supplier Count", value: String(report.vendor_count) },
                { key: "Months Covered", value: String(report.month_count) },
              ]}
              testId="biz-reconcile-kv"
            />

            {report.recommendations.length > 0 && (
              <div className="inv-reconcile__recommendations">
                <h4 className="inv-reconcile__rec-title">Recommendations</h4>
                <ul>
                  {report.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

// ─── Export ──────────────────────────────────────────────────────────────────

function ExportSection({ lastResult }: { lastResult: InvoiceProcessResponse | null }) {
  const { show: notify } = useNotification();

  const downloadJson = useCallback(() => {
    if (!lastResult) return;
    const blob = new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `business-invoice-analysis-${lastResult.analysis_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
    notify("ok", "JSON exported successfully.");
  }, [lastResult, notify]);

  const downloadCsv = useCallback(() => {
    if (!lastResult) return;
    const inv = lastResult.invoice;
    const rows = [
      ["Field", "Value"],
      ["Invoice Number", inv.number ?? ""],
      ["Date", inv.date ?? ""],
      ["Type", inv.type],
      ["Supplier/Vendor NTN", inv.seller_ntn ?? ""],
      ["Buyer NTN", inv.buyer_ntn ?? ""],
      ["Subtotal", String(inv.subtotal)],
      ["Tax Rate", String(inv.tax_rate ?? "")],
      ["Sales Tax Amount", String(inv.tax_amount)],
      ["Total", String(inv.total)],
      ["Validation Score", String(lastResult.validation.score)],
      ["Valid", String(lastResult.validation.is_valid)],
      ["Duplicate", String(lastResult.is_duplicate)],
      ["ITC Eligible", String(lastResult.itc_eligible)],
      ["Tax Impact", String(lastResult.tax_impact)],
    ];
    const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `business-invoice-analysis-${lastResult.analysis_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    notify("ok", "CSV exported successfully.");
  }, [lastResult, notify]);

  return (
    <div className="inv-export">
      <Button variant="ghost" size="sm" onClick={downloadJson} disabled={!lastResult} data-testid="biz-export-json">
        Export JSON
      </Button>
      <Button variant="ghost" size="sm" onClick={downloadCsv} disabled={!lastResult} data-testid="biz-export-csv">
        Export CSV
      </Button>
    </div>
  );
}

// ─── Dashboard Stats ────────────────────────────────────────────────────────

function DashboardCard({ dashboard }: { dashboard: InvoiceDashboard }) {
  return (
    <Card title="Business Invoice Dashboard" testId="biz-dashboard-card">
      <div className="inv-dashboard">
        <div className="inv-dashboard__stat">
          <span className="inv-dashboard__stat-value">{dashboard.total_invoices}</span>
          <span className="inv-dashboard__stat-label">Total Invoices</span>
        </div>
        <div className="inv-dashboard__stat">
          <span className="inv-dashboard__stat-value">{dashboard.sales_count}</span>
          <span className="inv-dashboard__stat-label">Sales</span>
        </div>
        <div className="inv-dashboard__stat">
          <span className="inv-dashboard__stat-value">{dashboard.purchases_count}</span>
          <span className="inv-dashboard__stat-label">Purchases</span>
        </div>
        <div className="inv-dashboard__stat inv-dashboard__stat--highlight">
          <span className="inv-dashboard__stat-value" style={{ color: "var(--c-err)" }}>
            {formatPkr(dashboard.net_payable)}
          </span>
          <span className="inv-dashboard__stat-label">Net Payable</span>
          <Tag
            variant={
              dashboard.payable_status === "paid" ? "ok" :
              dashboard.payable_status === "pending" ? "warn" :
              "accent"
            }
          >
            {dashboard.payable_status}
          </Tag>
        </div>
      </div>

      <div className="inv-dashboard__breakdown">
        <Kv
          rows={[
            { key: "Total Sales", value: formatPkr(dashboard.total_sales) },
            { key: "Total Purchases", value: formatPkr(dashboard.total_purchases) },
            { key: "Output Tax", value: formatPkr(dashboard.total_output_tax) },
            { key: "Input Tax", value: formatPkr(dashboard.total_input_tax) },
            { key: "Net Payable", value: formatPkr(dashboard.net_payable) },
            { key: "Status", value: (
              <Tag variant={
                dashboard.payable_status === "paid" ? "ok" :
                dashboard.payable_status === "pending" ? "warn" :
                "accent"
              }>
                {dashboard.payable_status}
              </Tag>
            ) },
          ]}
          testId="biz-dashboard-kv"
        />
      </div>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export function BusinessInvoicesPage() {
  const { show: notify } = useNotification();

  const [invoiceText, setInvoiceText] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InvoiceProcessResponse | null>(null);

  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [dashboard, setDashboard] = useState<InvoiceDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const [textError, setTextError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"process" | "reconcile">("process");

  // Fetch dashboard on mount
  const fetchDashboard = useCallback(async () => {
    setLoadingDashboard(true);
    setDashboardError(null);
    try {
      const data = await api.invoices.getDashboard();
      setDashboard(data);
    } catch (err) {
      if (err instanceof NetworkError) {
        setDashboardError("Cannot reach the server for the business invoice dashboard.");
      } else if (err instanceof ApiError) {
        setDashboardError(`Dashboard unavailable: ${err.detail}`);
      }
    } finally {
      setLoadingDashboard(false);
    }
  }, []);

  // Load dashboard on mount
  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  const process = useCallback(async () => {
    setTextError(null);
    setError(null);

    if (!invoiceText.trim()) {
      setTextError("Please paste invoice text before processing.");
      return;
    }
    if (invoiceText.trim().length < 15) {
      setTextError("Invoice text is too short. Please paste a more complete invoice.");
      return;
    }

    setProcessing(true);
    try {
      const resp = await api.invoices.process(
        invoiceText.trim(),
        invoiceId.trim() || undefined,
      );
      setResult(resp);
      notify("ok", "Business invoice processed successfully.");
      // Refresh dashboard
      void fetchDashboard();
    } catch (err) {
      if (err instanceof NetworkError) {
        setError("Cannot reach the server. Is the backend running?");
        notify("err", "Cannot reach the backend server.");
      } else if (err instanceof ApiError) {
        const msg = `Processing failed: ${err.detail}`;
        setError(msg);
        notify("err", msg);
      } else {
        setError("An unexpected error occurred during processing.");
        notify("err", "Unexpected error during invoice processing.");
      }
    } finally {
      setProcessing(false);
    }
  }, [invoiceText, invoiceId, notify, fetchDashboard]);

  const clear = useCallback(() => {
    setInvoiceText("");
    setInvoiceId("");
    setResult(null);
    setError(null);
    setTextError(null);
  }, []);

  return (
    <ErrorBoundary>
      <section className="page page--invoices">
        <header className="page__header">
          <div>
            <h2 className="page__title">Business Invoice Intelligence</h2>
            <p className="page__subtitle">
              Process, validate, and reconcile your business sales and supplier invoices — powered by the live backend pipeline with sales tax input/output tracking, ITC eligibility checking, and duplicate detection.
            </p>
          </div>
          <div className="page__header-actions">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void fetchDashboard()}
              data-testid="biz-refresh-btn"
            >
              Refresh Dashboard
            </Button>
          </div>
        </header>

        <div className="page__content">
          {/* Dashboard */}
          {loadingDashboard ? (
            <div className="inv-dashboard-loading">
              <Loading label="Loading business invoice dashboard…" testId="biz-dashboard-loading" />
            </div>
          ) : dashboardError ? (
            <StatusBanner
              kind="warn"
              title="Dashboard unavailable"
              description={dashboardError}
              testId="biz-dashboard-error"
            />
          ) : dashboard ? (
            <DashboardCard dashboard={dashboard} />
          ) : null}

          {/* Tab navigation */}
          <div className="inv-tabs" role="tablist" data-testid="biz-tabs">
            <button
              role="tab"
              aria-selected={activeTab === "process"}
              className={clsx("inv-tabs__tab", activeTab === "process" && "inv-tabs__tab--active")}
              onClick={() => setActiveTab("process")}
              data-testid="biz-tab-process"
            >
              Process Invoice
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "reconcile"}
              className={clsx("inv-tabs__tab", activeTab === "reconcile" && "inv-tabs__tab--active")}
              onClick={() => setActiveTab("reconcile")}
              data-testid="biz-tab-reconcile"
            >
              Sales Tax Reconciliation
            </button>
          </div>

          {/* Process Invoice */}
          {activeTab === "process" && (
            <>
              <Card
                title="Process a Business Invoice"
                subtitle="Paste invoice text to validate, extract details, check input tax (ITC) eligibility, and detect duplicates"
                testId="biz-process-card"
              >
                <div className="inv-process">
                  <Field
                    label="Invoice ID (optional)"
                    helperText="Provide a business invoice number or FBR reference if known"
                    data-testid="biz-id-field"
                  >
                    <input
                      type="text"
                      className="inv-process__id-input"
                      value={invoiceId}
                      onChange={(e) => setInvoiceId(e.target.value)}
                      placeholder="e.g. SINV-2024-001"
                      disabled={processing}
                      data-testid="biz-id-input"
                    />
                  </Field>

                  <Field
                    label="Invoice Text"
                    error={textError ?? undefined}
                    data-testid="biz-text-field"
                  >
                    <textarea
                      className="inv-process__textarea"
                      value={invoiceText}
                      onChange={(e) => {
                        setInvoiceText(e.target.value);
                        setTextError(null);
                      }}
                      placeholder="Paste the text of a business sales or supplier purchase invoice here. Include the invoice number, date, supplier/vendor NTN, amounts, and sales tax rate if visible…"
                      rows={8}
                      disabled={processing}
                      data-testid="biz-text-input"
                    />
                  </Field>

                  <div className="inv-process__meta">
                    <span className="small muted">{invoiceText.length} characters</span>
                  </div>

                  <div className="inv-process__actions">
                    <Button
                      variant="primary"
                      loading={processing}
                      disabled={processing}
                      onClick={() => void process()}
                      data-testid="biz-process-button"
                    >
                      {processing ? "Processing…" : "Process Invoice"}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={processing}
                      onClick={clear}
                      data-testid="biz-clear-button"
                    >
                      Clear
                    </Button>
                    <ExportSection lastResult={result} />
                  </div>
                </div>
              </Card>

              {/* Processing error */}
              {error ? (
                <StatusBanner
                  kind="err"
                  title="Processing failed"
                  description={error}
                  testId="biz-error"
                />
              ) : null}

              {/* Processing loading */}
              {processing && (
                <Loading
                  label="Processing business invoice… Extracting details, validating format, checking for duplicates and ITC eligibility."
                  testId="biz-processing"
                />
              )}

              {/* Result */}
              {result && !processing && (
                <ProcessResultView result={result} />
              )}

              {/* Empty state */}
              {!result && !processing && !error && (
                <StatusBanner
                  kind="info"
                  title="Paste a business invoice to begin"
                  description="Use the form above to paste invoice text. The pipeline will extract invoice details, validate the format, check for duplicates, and determine ITC eligibility against your sales tax output."
                  testId="biz-empty-state"
                />
              )}
            </>
          )}

          {/* Reconcile */}
          {activeTab === "reconcile" && (
            <ReconcileView />
          )}
        </div>
      </section>

      <style>{`
        /* Dashboard */
        .inv-dashboard-loading {
          padding: var(--s-6);
          text-align: center;
        }

        .inv-dashboard {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: var(--s-4);
          margin-bottom: var(--s-5);
        }

        @media (max-width: 768px) {
          .inv-dashboard {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        @media (max-width: 480px) {
          .inv-dashboard {
            grid-template-columns: 1fr;
          }
        }

        .inv-dashboard__stat {
          padding: var(--s-4);
          background: var(--c-paper-2);
          border-radius: var(--r-2);
          text-align: center;
        }

        .inv-dashboard__stat--highlight {
          background: var(--c-accent-soft);
          border: 1px solid rgba(13, 107, 79, 0.2);
        }

        .inv-dashboard__stat-value {
          display: block;
          font-family: var(--f-display);
          font-size: 22px;
          font-weight: 700;
          margin-bottom: 2px;
        }

        .inv-dashboard__stat-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--c-text-muted);
        }

        .inv-dashboard__breakdown {
          border-top: 1px dashed var(--c-line);
          padding-top: var(--s-4);
        }

        /* Tabs */
        .inv-tabs {
          display: flex;
          gap: 0;
          border-bottom: 2px solid var(--c-line);
          margin-bottom: var(--s-5);
        }

        .inv-tabs__tab {
          padding: var(--s-3) var(--s-5);
          background: transparent;
          border: 0;
          border-bottom: 2px solid transparent;
          margin-bottom: -2px;
          font-size: 14px;
          font-weight: 500;
          color: var(--c-text-muted);
          cursor: pointer;
          transition: color var(--t-fast) var(--ease), border-color var(--t-fast) var(--ease);
        }

        .inv-tabs__tab:hover {
          color: var(--c-text);
        }

        .inv-tabs__tab--active {
          color: var(--c-accent);
          border-bottom-color: var(--c-accent);
        }

        /* Process form */
        .inv-process__id-input {
          width: 100%;
          padding: 8px 12px;
          border: 1px solid var(--c-line-strong);
          border-radius: var(--r-2);
          background: #fffaf0;
          font-size: 14px;
        }

        .inv-process__id-input:focus {
          outline: 2px solid var(--c-accent);
          outline-offset: -1px;
          border-color: var(--c-accent);
        }

        .inv-process__textarea {
          width: 100%;
          padding: var(--s-4);
          border: 1px solid var(--c-line-strong);
          border-radius: var(--r-2);
          background: #fffaf0;
          font-family: var(--f-body);
          font-size: 14px;
          line-height: 1.6;
          resize: vertical;
          min-height: 180px;
        }

        .inv-process__textarea:focus {
          outline: 2px solid var(--c-accent);
          outline-offset: -1px;
          border-color: var(--c-accent);
        }

        .inv-process__meta {
          margin-top: var(--s-2);
          text-align: right;
        }

        .inv-process__actions {
          display: flex;
          gap: var(--s-3);
          margin-top: var(--s-4);
          align-items: center;
          flex-wrap: wrap;
        }

        /* Result */
        .inv-result {
          display: flex;
          flex-direction: column;
          gap: var(--s-5);
        }

        .inv-result__status {
          /* status banner handles it */
        }

        .inv-result__badges {
          display: flex;
          flex-direction: column;
          gap: var(--s-3);
        }

        /* Validation score */
        .inv-validation__score-row {
          display: flex;
          align-items: center;
          gap: var(--s-3);
          margin-bottom: var(--s-4);
        }

        .inv-validation__score-label {
          font-size: 13px;
          font-weight: 600;
          min-width: 120px;
          color: var(--c-text-muted);
        }

        .inv-validation__score-bar {
          flex: 1;
          height: 8px;
          background: var(--c-line);
          border-radius: 999px;
          overflow: hidden;
        }

        .inv-validation__score-fill {
          height: 100%;
          border-radius: 999px;
          transition: width 0.6s ease, background 0.4s ease;
        }

        .inv-validation__score-number {
          font-size: 14px;
          font-weight: 700;
          min-width: 52px;
          text-align: right;
        }

        /* Invoice issues */
        .inv-issues {
          display: flex;
          flex-direction: column;
          gap: var(--s-4);
        }

        .inv-issues__group-head {
          margin-bottom: var(--s-2);
        }

        .inv-issues__list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: var(--s-2);
        }

        .inv-issues__item {
          display: flex;
          gap: var(--s-3);
          padding: var(--s-3) var(--s-4);
          border-radius: var(--r-2);
          font-size: 13px;
        }

        .inv-issues__item--error {
          background: #fdf5f5;
          border-left: 3px solid var(--c-err);
        }

        .inv-issues__item--warning {
          background: #fdf8ec;
          border-left: 3px solid var(--c-warn);
        }

        .inv-issues__item--info {
          background: var(--c-accent-soft);
          border-left: 3px solid var(--c-accent);
        }

        .inv-issues__field {
          font-family: var(--f-mono);
          font-size: 12px;
          font-weight: 600;
          min-width: 120px;
          color: var(--c-text-muted);
        }

        .inv-issues__message {
          flex: 1;
          color: var(--c-text);
        }

        .inv-issues-empty {
          padding: var(--s-4);
          text-align: center;
        }

        /* Summary */
        .inv-summary__text {
          font-size: 13.5px;
          line-height: 1.7;
          margin-bottom: var(--s-3);
        }

        .inv-summary__meta {
          margin-top: var(--s-3);
          padding-top: var(--s-3);
          border-top: 1px dashed var(--c-line);
        }

        /* Reconcile */
        .inv-reconcile {
          display: flex;
          flex-direction: column;
          gap: var(--s-4);
        }

        .inv-reconcile__fields {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: var(--s-4);
        }

        @media (max-width: 768px) {
          .inv-reconcile__fields {
            grid-template-columns: 1fr;
          }
        }

        .inv-reconcile__textarea {
          width: 100%;
          padding: var(--s-3);
          border: 1px solid var(--c-line-strong);
          border-radius: var(--r-2);
          background: #fffaf0;
          font-family: var(--f-mono);
          font-size: 12px;
          line-height: 1.5;
          resize: vertical;
          min-height: 120px;
        }

        .inv-reconcile__textarea:focus {
          outline: 2px solid var(--c-accent);
          outline-offset: -1px;
          border-color: var(--c-accent);
        }

        .inv-reconcile__actions {
          display: flex;
          gap: var(--s-3);
          align-items: center;
        }

        .inv-reconcile__report {
          margin-top: var(--s-4);
          padding: var(--s-5);
          background: var(--c-paper-2);
          border-radius: var(--r-2);
          border: 1px solid var(--c-line);
        }

        .inv-reconcile__report-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: var(--s-4);
        }

        .inv-reconcile__report-title {
          font-family: var(--f-display);
          font-size: 16px;
          margin: 0;
        }

        .inv-reconcile__recommendations {
          margin-top: var(--s-4);
          padding-top: var(--s-4);
          border-top: 1px dashed var(--c-line);
        }

        .inv-reconcile__rec-title {
          font-size: 13px;
          font-weight: 700;
          margin-bottom: var(--s-2);
        }

        .inv-reconcile__recommendations ul {
          margin: 0;
          padding-left: var(--s-5);
          font-size: 13px;
          display: flex;
          flex-direction: column;
          gap: var(--s-1);
        }

        /* Export */
        .inv-export {
          margin-left: auto;
          display: flex;
          gap: var(--s-2);
        }

        /* Page header actions */
        .page__header-actions {
          display: flex;
          gap: var(--s-2);
          align-items: center;
        }
      `}</style>
    </ErrorBoundary>
  );
}