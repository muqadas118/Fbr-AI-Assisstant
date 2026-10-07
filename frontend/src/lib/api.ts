// ---------------------------------------------------------------------------
// API client — single typed entry point for the FBR backend.
// One file, one fetch helper, one typed surface area.
// ---------------------------------------------------------------------------

import { getStoredAuthToken } from "@/state/auth";

const DEFAULT_TIMEOUT_MS = 30_000;
// Full RAG pipeline (FAISS + embeddings + LLM) can take well over a minute:
// cold-start model load plus one slow provider round-trip per routed domain.
const ANSWER_TIMEOUT_MS = 300_000;

// ============================================================================
// Core Types
// ============================================================================

export interface SourceItem {
  chunk_id: string;
  document_id: string;
  source: string;
  source_path: string;
  source_sha256: string | null;
  page: number | null;
  page_start: number | null;
  page_end: number | null;
  section: string | null;
  section_reference: string | null;
  section_number: string | null;
  law_tag: string | null;
  multi_law_candidate: boolean;
  score: number;
  semantic_score: number;
  bm25_score: number;
  exact_match: boolean;
}

export interface VerificationCheck {
  passed: boolean;
  reason: string;
  weak_sentences?: string[] | null;
}

export interface VerificationChecks {
  answer_size: VerificationCheck;
  section_consistency: VerificationCheck;
  grounding: VerificationCheck;
  speculation: VerificationCheck;
}

export interface VerificationResult {
  passed: boolean;
  checks: VerificationChecks;
  failed_checks: string[];
  reason: string;
}

export interface AnswerResponse {
  question: string;
  domains: string[];
  primary_domain: string;
  multi_domain: boolean;
  routing: Record<string, unknown>;
  domain_results: Array<Record<string, unknown>>;
  answer: string;
  sources: SourceItem[];
  verification: VerificationResult;
  grounded: boolean;
}

export interface AssistantToolRun {
  tool: string;
  ok: boolean;
  summary: string;
  data: unknown;
}

export interface AssistantAskResponse {
  question: string;
  answer: string;
  tools_used: AssistantToolRun[];
  sources: SourceItem[];
  verification: VerificationResult;
  grounded: boolean;
  mode: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  auth?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  constructor(message: string, status: number, detail: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

// ============================================================================
// Calendar Types
// ============================================================================

export interface CalendarEvent {
  id: string;
  title: string;
  description?: string;
  due_date: string;
  fiscal_year: number;
  tax_year?: number;
  quarter?: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  event_type: string;
  legal_reference?: string;
  penalty?: string;
  days_remaining: number;
  is_overdue: boolean;
  is_completed: boolean;
  extension_available: boolean;
  extension_date?: string;
}

export interface UpcomingTask {
  event_id: string;
  title: string;
  due_date: string;
  days_remaining: number;
  priority: string;
  category: string;
  event_type: string;
  is_overdue: boolean;
  urgency: string;
  action_required: string;
}

export interface CalendarSummary {
  by_category: Record<string, number>;
  by_priority: Record<string, number>;
  by_month: Record<string, number>;
  by_type: Record<string, number>;
}

export interface CalendarDashboard {
  taxpayer_type: string;
  compliance_score: number;
  compliance_grade: string;
  total_events: number;
  overdue_count: number;
  critical_upcoming_30d: number;
  critical_upcoming_7d: number;
  next_7_days_tasks: Array<{
    title: string;
    due_date: string;
    days_remaining: number;
  }>;
  compliance_grade_color: string;
  summary_message: string;
}

export interface CalendarResponse {
  query: Record<string, unknown>;
  total_events: number;
  events: CalendarEvent[];
  summary: CalendarSummary;
  upcoming_tasks: UpcomingTask[];
  overdue_events: CalendarEvent[];
  compliance_score: number;
  compliance_grade: string;
  recommendations: string[];
  generated_at: string;
}

export interface ReminderResponse {
  event_id: string;
  reminders_scheduled: number;
  reminder_ids: string[];
}

// ============================================================================
// Tax Health Types
// ============================================================================

export interface HealthIssue {
  code: string;
  title: string;
  description: string;
  severity: string;
  tax_impact: number;
  penalty_estimate: number;
}

export interface HealthRecommendation {
  priority: string;
  action: string;
  reason: string;
  deadline?: string;
}

export interface TaxHealthResponse {
  ntn: string;
  tax_year: number;
  health_score: number;
  health_grade: string;
  risk_level: string;
  itr_filed: boolean;
  itr_filing_date?: string;
  itr_due_date?: string;
  declared_income: number;
  estimated_income: number;
  tax_assessed: number;
  tax_paid: number;
  tax_outstanding: number;
  wht_collected: number;
  wht_deposited: number;
  wht_shortfall: number;
  st_collected: number;
  st_deposited: number;
  st_shortfall: number;
  filing_score: number;
  deposit_score: number;
  compliance_score: number;
  reconciliation_score: number;
  issues: HealthIssue[];
  critical_issues_count: number;
  total_penalty_exposure: number;
  recommendations: HealthRecommendation[];
  generated_at: string;
}

export interface RiskFactor {
  code: string;
  description: string;
  level: string;
  weight: number;
  mitigation?: string;
}

export interface RiskAnalysisResponse {
  risk_level: string;
  risk_score: number;
  factors: RiskFactor[];
}

// ============================================================================
// Notice Types
// ============================================================================

export interface ActionStep {
  step_number: number;
  title: string;
  description: string;
  documents_needed: string[];
  estimated_hours: number;
  priority: string;
}

export interface ActionPlan {
  notice_type: string;
  summary: string;
  total_steps: number;
  estimated_total_hours: number;
  requires_professional_help: boolean;
  requires_payment: boolean;
  steps: ActionStep[];
  common_mistakes: string[];
  helpful_tips: string[];
  references: string[];
}

export interface AppealGuide {
  is_appealable: boolean;
  forum: string;
  time_limit_days: number;
  forms_required: string[];
  documents_needed: string[];
  fees_required: string;
  common_grounds: string[];
  success_factors: string[];
  typical_success_rate: string;
  estimated_cost: string;
  notes: string[];
}

export interface NoticeAnalysisResponse {
  analysis_id: string;
  timestamp: string;
  duration_ms: number;
  notice_type: string;
  confidence: number;
  is_critical: boolean;
  is_appealable: boolean;
  taxpayer_name?: string;
  taxpayer_ntn?: string;
  notice_id?: string;
  issue_date?: string;
  tax_years: string[];
  sections_cited: string[];
  total_demanded?: number;
  tax_amount?: number;
  penalty_amount?: number;
  deadline_date?: string;
  days_remaining?: number;
  urgency_level: string;
  action_plan?: ActionPlan;
  appeal_guide?: AppealGuide;
  formatted_text: string;
  summary: string;
}

// ============================================================================
// Document Types
// ============================================================================

export interface ExtractedInfo {
  person_name?: string;
  person_cnic?: string;
  person_ntn?: string;
  company_name?: string;
  company_ntn?: string;
  reference_number?: string;
  issue_date?: string;
  total_amount?: number;
  net_amount?: number;
  currency: string;
  tax_rate?: number;
  tax_amount?: number;
  tax_section?: string;
  fbr_reference?: string;
  address?: string;
  extraction_quality: number;
}

export interface ParsedForm {
  form_type: string;
  form_number?: string;
  tax_year?: string;
  employer_info: Record<string, unknown>;
  employee_info: Record<string, unknown>;
  salary_details: Record<string, unknown>;
  tax_details: Record<string, unknown>;
  wht_details: Record<string, unknown>;
  income_details: Record<string, unknown>;
  deductions: Record<string, unknown>;
  fields_extracted: number;
  total_fields: number;
  extraction_rate: number;
  notes: string[];
}

export interface DocumentAnalysisResponse {
  analysis_id: string;
  timestamp: string;
  duration_ms: number;
  document_type: string;
  document_category: string;
  classification_confidence: number;
  matched_signals: string[];
  extracted_info: ExtractedInfo;
  parsed_form?: ParsedForm;
  overall_quality_score: number;
  is_readable: boolean;
  needs_ocr: boolean;
  formatted_text: string;
  summary: string;
}

export interface DocumentVerifyResponse {
  ntn?: string;
  cnic?: string;
  name?: string;
  confidence: number;
  extraction_quality: number;
}

// ============================================================================
// Invoice Types
// ============================================================================

export interface InvoiceIssue {
  field: string;
  message: string;
  severity: string;
}

export interface InvoiceValidation {
  is_valid: boolean;
  score: number;
  errors: number;
  warnings: number;
  issues: InvoiceIssue[];
}

export interface InvoiceData {
  id: string;
  number?: string;
  date?: string;
  type: string;
  seller_ntn?: string;
  buyer_ntn?: string;
  subtotal: number;
  tax_rate: number;
  tax_amount: number;
  total: number;
}

export interface InvoiceProcessResponse {
  analysis_id: string;
  invoice: InvoiceData;
  validation: InvoiceValidation;
  is_duplicate: boolean;
  duplicate_of?: string;
  itc_eligible: boolean;
  tax_impact: number;
  summary: string;
  duration_ms: number;
}

export interface InvoiceDashboard {
  total_invoices: number;
  sales_count: number;
  purchases_count: number;
  total_sales: number;
  total_purchases: number;
  total_output_tax: number;
  total_input_tax: number;
  net_payable: number;
  payable_status: string;
}

export interface ReconciliationReport {
  total_invoices: number;
  total_sales: number;
  total_purchases: number;
  total_output_tax: number;
  total_input_tax: number;
  net_payable: number;
  vendor_count: number;
  month_count: number;
  confidence_score: number;
  recommendations: string[];
}

// ============================================================================
// Verification Types
// ============================================================================

export interface VerificationResponse {
  request_type: string;
  value: string;
  is_verified: boolean;
  confidence: number;
  message: string;
  details: Record<string, unknown>;
}

// ============================================================================
// Vault Types
// ============================================================================

export interface VaultDocument {
  id: string;
  user_id: string;
  filename: string;
  type: string;
  content: string;
  size: string;
  secure: boolean;
  date: string;
  updated_at: string;
}

// ============================================================================
// Monitor Types
// ============================================================================

export interface MonitorEvent {
  id: string;
  type: string;
  severity: string;
  title: string;
  description: string;
  status: string;
  requires_action: boolean;
  detected_at: string;
  reference_number?: string;
  action_deadline?: string;
}

export interface MonitorDashboard {
  user_id: string;
  total_events: number;
  unread_count: number;
  critical_count: number;
  action_required: number;
  recent_events: MonitorEvent[];
  critical_events: Array<{
    id: string;
    title: string;
    description: string;
    action_deadline?: string;
  }>;
  statistics: Record<string, unknown>;
}

// ============================================================================
// Team Types
// ============================================================================

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  ntn?: string;
  organization?: string;
  created_at: string;
  last_login_at?: string;
}

export interface TeamMember {
  id: string;
  team_id: string;
  user_id: string;
  role: string;
  joined_at: string;
  is_active: boolean;
}

export interface Team {
  id: string;
  name: string;
  owner_id: string;
  organization_type?: string;
  ntn?: string;
  plan: string;
  is_active: boolean;
  member_count: number;
  created_at: string;
}

export interface UserDashboard {
  user: UserProfile;
  team_count: number;
  teams: Team[];
  active_sessions: number;
  pending_invitations: Array<{
    id: string;
    team_id: string;
    email: string;
    role: string;
    status: string;
    invited_at: string;
    expires_at: string;
  }>;
}

export interface TeamDashboard {
  team: Team;
  member_count: number;
  members: TeamMember[];
  pending_invitations: number;
  invitations: Array<{
    id: string;
    team_id: string;
    email: string;
    role: string;
    status: string;
    invited_at: string;
    expires_at: string;
  }>;
}

// ============================================================================
// Business Report Types
// ============================================================================

export interface BusinessReportResponse {
  report_type: string;
  format: string;
  generated_at?: string | null;
  content: string;
  sections_available: string[];
  sections_unavailable: string[];
  errors: string[];
}

// ============================================================================
// API Client Implementation
// ============================================================================

function readEnvString(name: string, fallback: string): string {
  const value = (import.meta.env as unknown as Record<string, string | undefined>)[name];
  return value && value.length > 0 ? value : fallback;
}

function readEnvNumber(name: string, fallback: number): number {
  const value = (import.meta.env as unknown as Record<string, string | undefined>)[name];
  if (!value) return fallback;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export interface ApiClientConfig {
  baseUrl: string;
  timeoutMs: number;
  /** Optional explicit headers (merged over auth/defaults). Used by authApi. */
  headers?: Record<string, string>;
}

export function getApiConfig(): ApiClientConfig {
  return {
    baseUrl: readEnvString("VITE_API_BASE_URL", "http://127.0.0.1:8000").replace(/\/$/, ""),
    timeoutMs: readEnvNumber("VITE_API_TIMEOUT_MS", DEFAULT_TIMEOUT_MS),
  };
}

// ============================================================================
// Auth token injection (Supabase JWT -> Bearer header).
// Does NOT change any of the 44 leaf method signatures: the central
// request() helper awaits the getter and merges the header.
// Wire once at startup: setAuthTokenGetter(getAccessToken).
// ============================================================================

export type AuthTokenGetter = () => Promise<string | null>;

let authTokenGetter: AuthTokenGetter | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAuthTokenGetter(fn: AuthTokenGetter | null): void {
  authTokenGetter = fn;
}

/** Register the app-level response to an expired or rejected session. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!authTokenGetter) return {};
  try {
    const token = await authTokenGetter();
    return token ? { Authorization: "Bearer " + token } : {};
  } catch {
    return {};
  }
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  init: { body?: unknown } = {},
  config: ApiClientConfig = getApiConfig(),
): Promise<T> {
  const url = `${config.baseUrl}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.timeoutMs);

  const auth = await authHeaders();

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...auth,
        ...config.headers,
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new NetworkError(`Request to ${path} timed out after ${config.timeoutMs}ms`);
    }
    throw new NetworkError(
      err instanceof Error ? err.message : `Network error contacting ${path}`,
    );
  } finally {
    clearTimeout(timer);
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text.length > 0) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (!response.ok) {
    const rawDetail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    const detail =
      response.status === 401
        ? "Authentication required — please login (session missing or expired)."
        : rawDetail;
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(`${method} ${path} failed: ${response.status}`, response.status, detail);
  }

  return payload as T;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

// ---------------------------------------------------------------------------
// First-party Auth (POST /auth/signup | /auth/login | /auth/logout | /auth/me)
// Opaque bearer session tokens issued by the FastAPI backend itself.
// ---------------------------------------------------------------------------

export interface AuthUserPayload {
  id: string;
  email: string;
  name: string;
  role: string;
  organization?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface AuthSessionResponse {
  user: AuthUserPayload;
  token: string;
  expires_at?: string;
  token_type?: string;
}

export interface AuthMeResponse {
  user: AuthUserPayload;
  source?: string;
}

export const authApi = {
  signup(email: string, password: string, name?: string): Promise<AuthSessionResponse> {
    return request("POST", "/auth/signup", {
      body: { email, password, ...(name ? { name } : {}) },
    });
  },

  login(email: string, password: string): Promise<AuthSessionResponse> {
    return request("POST", "/auth/login", { body: { email, password } });
  },

  logout(token: string): Promise<{ success: boolean }> {
    return request("POST", "/auth/logout", {}, {
      ...getApiConfig(),
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  me(token: string): Promise<AuthMeResponse> {
    return request("GET", "/auth/me", {}, {
      ...getApiConfig(),
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  /** Persist the onboarding choice: the user's primary workspace. */
  allocateWorkspace(
    workspaceType: "personal" | "business",
    token?: string,
  ): Promise<{ user: AuthUserPayload; preferred_workspace: string }> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const explicit = token ?? getStoredAuthToken();
    if (explicit) headers.Authorization = `Bearer ${explicit}`;
    else return Promise.reject(new Error("Authentication required — please login."));
    return request("POST", "/auth/workspace", { body: { workspace_type: workspaceType } }, {
      ...getApiConfig(),
      headers,
    });
  },
};

// ============================================================================
// File Upload (multipart) helper + types
// ============================================================================

export interface UploadMeta {
  filename: string;
  content_family: "pdf" | "image" | "text";
  size_bytes: number;
  pages?: number | null;
  ocr_simulated: boolean;
  ocr_warning?: string | null;
}

export interface UploadDocumentAnalysisResponse {
  meta: UploadMeta;
  // Full DocumentAnalysis payload from the backend pipeline.
  analysis: {
    analysis_id: string;
    timestamp: string;
    document_type: string;
    document_category: string;
    classification_confidence: number;
    extracted_info: ExtractedInfo & { [key: string]: unknown };
    formatted_text: string;
    summary?: string | null;
    ocr_simulated: boolean;
    ocr_warning?: string | null;
    [key: string]: unknown;
  };
}

export interface UploadDocumentVerifyResponse {
  meta: UploadMeta;
  ntn?: string | null;
  cnic?: string | null;
  name?: string | null;
  confidence: number;
  extraction_quality: number;
  ntn_format_valid: boolean;
  cnic_format_valid: boolean;
}

export interface UploadInvoiceProcessResponse {
  meta: UploadMeta;
  result: InvoiceProcessResponse;
}

async function uploadRequest<T>(
  path: string,
  file: File,
  fields: Record<string, string> = {},
  config: ApiClientConfig = getApiConfig(),
): Promise<T> {
  const url = `${config.baseUrl}${path}`;
  const controller = new AbortController();
  // File extraction (PDF/OCR) can be slower than JSON endpoints.
  const timeoutMs = Math.max(config.timeoutMs, 60_000);
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const auth = await authHeaders();
  const form = new FormData();
  form.append("file", file, file.name);
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json", ...auth },
      body: form,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new NetworkError(`Upload to ${path} timed out after ${timeoutMs}ms`);
    }
    throw new NetworkError(
      err instanceof Error ? err.message : `Network error uploading to ${path}`,
    );
  } finally {
    clearTimeout(timer);
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text.length > 0) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (!response.ok) {
    const rawDetail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    const detail =
      response.status === 401
        ? "Authentication required — please login (session missing or expired)."
        : rawDetail;
    if (response.status === 401) unauthorizedHandler?.();
    throw new ApiError(`POST ${path} failed: ${response.status}`, response.status, detail);
  }

  return payload as T;
}

// ============================================================================
// API Methods
// ============================================================================

export const api = {
  // ---------------------------------------------------------------------------
  // Core
  // ---------------------------------------------------------------------------
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("GET", "/health");
  },

  // ---------------------------------------------------------------------------
  // Q&A
  // ---------------------------------------------------------------------------
  answer(query: string): Promise<AnswerResponse> {
    return request<AnswerResponse>(
      "POST",
      "/answer",
      { body: { query } },
      { ...getApiConfig(), timeoutMs: ANSWER_TIMEOUT_MS },
    );
  },

  /**
   * Smart assistant: AI plans and uses every backend tool (calculators,
   * verification, notices, documents, invoices, calendar, health) and
   * grounds the answer in the FBR corpus. Optional file upload (PDF/
   * image/text) is read by the backend pipeline before answering.
   */
  assistantAsk(query: string, file?: File | null): Promise<AssistantAskResponse> {
    if (file) {
      return uploadRequest<AssistantAskResponse>(
        "/assistant/ask",
        file,
        { query },
        { ...getApiConfig(), timeoutMs: ANSWER_TIMEOUT_MS },
      );
    }
    return request<AssistantAskResponse>(
      "POST",
      "/assistant/ask",
      { body: { query } },
      { ...getApiConfig(), timeoutMs: ANSWER_TIMEOUT_MS },
    );
  },

  /**
   * Streaming variant of assistantAsk (Server-Sent Events).
   * Calls onMeta once with the tool/verification payload, then onDelta
   * for each answer text chunk. Resolves with the assembled response
   * when the stream completes. Falls back to the plain endpoint when
   * the stream cannot even be opened (e.g. older backend).
   */
  async assistantAskStream(
    query: string,
    handlers: {
      onMeta?: (meta: Partial<AssistantAskResponse>) => void;
      onDelta?: (chunk: string) => void;
    },
  ): Promise<AssistantAskResponse> {
    const config = getApiConfig();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ANSWER_TIMEOUT_MS);
    try {
      const auth = await authHeaders();
      let response: Response;
      try {
        response = await fetch(`${config.baseUrl}/assistant/ask/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...auth },
          body: JSON.stringify({ query }),
          signal: controller.signal,
        });
      } catch (err) {
        throw new NetworkError(
          err instanceof Error ? err.message : "Network error contacting /assistant/ask/stream",
        );
      }
      if (!response.ok || !response.body) {
        // Non-streaming failure — let the plain endpoint produce a typed error.
        if (response.status === 429 || response.status === 422 || response.status === 401) {
          let detail = `HTTP ${response.status}`;
          try {
            const j = await response.json();
            if (j && typeof j === "object" && "detail" in j) detail = String((j as { detail: unknown }).detail);
          } catch { /* keep default */ }
          if (response.status === 401) unauthorizedHandler?.();
          throw new ApiError("POST /assistant/ask/stream failed", response.status, detail);
        }
        return this.assistantAsk(query);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const dataAcc: string[] = [];
      let meta: Partial<AssistantAskResponse> = {};
      let text = "";
      let eventName = "message";
      const handleEvent = () => {
        const data = dataAcc.join("\n");
        dataAcc.length = 0;
        if (eventName === "meta") {
          try { meta = JSON.parse(data) as Partial<AssistantAskResponse>; } catch { meta = {}; }
          handlers.onMeta?.(meta);
        } else if (eventName === "delta") {
          try {
            const chunk = JSON.parse(data) as string;
            text += chunk;
            handlers.onDelta?.(chunk);
          } catch { /* ignore malformed chunk */ }
        } else if (eventName === "verification") {
          // Post-stream verification settles after the tokens (backend runs
          // the verify pipeline after streaming so answers arrive instantly).
          // A failed grounding carries replacement_answer — the deterministic
          // refusal replaces the streamed prose (grounded-answer contract).
          try {
            const v = JSON.parse(data) as AssistantAskResponse["verification"];
            meta = { ...meta, verification: v };
            const replacement = (v as { replacement_answer?: string }).replacement_answer;
            if (replacement) text = replacement;
            handlers.onMeta?.(meta);
          } catch { /* ignore malformed verification */ }
        }
        eventName = "message";
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf("\n")) !== -1) {
          let line = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 1);
          if (line.endsWith("\r")) line = line.slice(0, -1);
          if (line === "") { handleEvent(); continue; }
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) dataAcc.push(line.slice(5).trimStart());
        }
      }
      if (dataAcc.length) handleEvent();

      return {
        question: meta.question ?? query,
        answer: text || (meta as { answer?: string }).answer || "",
        tools_used: meta.tools_used ?? [],
        sources: meta.sources ?? [],
        verification: meta.verification ?? {
          passed: false,
          checks: {
            answer_size: { passed: false, reason: "unavailable" },
            section_consistency: { passed: false, reason: "unavailable" },
            grounding: { passed: false, reason: "unavailable" },
            speculation: { passed: false, reason: "unavailable" },
          },
          failed_checks: [],
          reason: "no verification data",
        },
        grounded: meta.grounded ?? false,
        mode: meta.mode ?? "stream",
      } satisfies AssistantAskResponse;
    } finally {
      clearTimeout(timer);
    }
  },

  // ---------------------------------------------------------------------------
  // Calculations
  // ---------------------------------------------------------------------------
  calculate(calcType: string, inputs: Record<string, unknown>): Promise<Record<string, unknown>> {
    return request("POST", "/calculate", { body: { calc_type: calcType, inputs } });
  },

  getCalculationTypes(): Promise<Record<string, unknown>> {
    return request("GET", "/calculate/types");
  },

  // ---------------------------------------------------------------------------
  // Calendar
  // ---------------------------------------------------------------------------
  calendar: {
    get(params?: {
      taxpayer_type?: string;
      fiscal_year?: number;
      start_date?: string;
      end_date?: string;
      event_type?: string;
      category?: string;
      priority?: string;
      limit?: number;
    }): Promise<CalendarResponse> {
      const searchParams = new URLSearchParams();
      if (params?.taxpayer_type) searchParams.set("taxpayer_type", params.taxpayer_type);
      if (params?.fiscal_year) searchParams.set("fiscal_year", String(params.fiscal_year));
      if (params?.start_date) searchParams.set("start_date", params.start_date);
      if (params?.end_date) searchParams.set("end_date", params.end_date);
      if (params?.event_type) searchParams.set("event_type", params.event_type);
      if (params?.category) searchParams.set("category", params.category);
      if (params?.priority) searchParams.set("priority", params.priority);
      if (params?.limit) searchParams.set("limit", String(params.limit));
      const qs = searchParams.toString();
      return request<CalendarResponse>("GET", `/calendar${qs ? `?${qs}` : ""}`);
    },

    getUpcoming(taxpayerType = "individual", days = 30): Promise<UpcomingTask[]> {
      return request<UpcomingTask[]>(
        "GET",
        `/calendar/upcoming?taxpayer_type=${taxpayerType}&days=${days}`,
      );
    },

    getDashboard(taxpayerType = "individual"): Promise<CalendarDashboard> {
      return request<CalendarDashboard>(
        "GET",
        `/calendar/dashboard?taxpayer_type=${taxpayerType}`,
      );
    },

    markComplete(eventId: string): Promise<{ event_id: string; completed: boolean }> {
      return request("POST", `/calendar/events/${eventId}/complete`);
    },

    scheduleReminder(
      eventId: string,
      recipient: string,
      channels?: string[],
    ): Promise<ReminderResponse> {
      return request<ReminderResponse>("POST", "/calendar/reminders", {
        body: { event_id: eventId, recipient, channels: channels || ["email", "push"] },
      });
    },

    getTypes(): Promise<{ event_types: string[]; categories: string[]; priorities: string[] }> {
      return request("GET", "/calendar/types");
    },
  },

  // ---------------------------------------------------------------------------
  // Tax Health
  // ---------------------------------------------------------------------------
  taxHealth: {
    check(data: {
      ntn: string;
      tax_year?: number;
      itr_filed?: boolean;
      itr_filing_date?: string;
      itr_due_date?: string;
      declared_income?: number;
      estimated_income?: number;
      tax_assessed?: number;
      tax_paid?: number;
      wht_collected?: number;
      wht_deposited?: number;
      st_collected?: number;
      st_deposited?: number;
      notices_outstanding?: number;
    }): Promise<TaxHealthResponse> {
      return request<TaxHealthResponse>("POST", "/tax/health/check", { body: data });
    },

    analyzeRisks(data: {
      tax_outstanding?: number;
      notices_count?: number;
      itr_filed?: boolean;
      wht_shortfall?: number;
      st_shortfall?: number;
      estimated_income?: number;
      declared_income?: number;
    }): Promise<RiskAnalysisResponse> {
      return request<RiskAnalysisResponse>("POST", "/tax/health/risks", { body: data });
    },

    estimatePenalties(data: {
      tax_assessed?: number;
      tax_paid?: number;
      days_late_itr?: number;
      days_late_payment?: number;
      wht_shortfall?: number;
      st_shortfall?: number;
      is_concealment?: boolean;
    }): Promise<Record<string, unknown>> {
      return request("POST", "/tax/health/penalties", { body: data });
    },

    getScoreGuide(): Promise<Record<string, unknown>> {
      return request("GET", "/tax/health/score-guide");
    },
  },

  // ---------------------------------------------------------------------------
  // Notices
  // ---------------------------------------------------------------------------
  notices: {
    analyze(text: string, noticeId?: string): Promise<NoticeAnalysisResponse> {
      return request<NoticeAnalysisResponse>("POST", "/notices/analyze", {
        body: { text, notice_id: noticeId },
      });
    },

    getTypes(): Promise<{ total: number; notice_types: string[]; categories: string[] }> {
      return request("GET", "/notices/types");
    },
  },

  // ---------------------------------------------------------------------------
  // Documents
  // ---------------------------------------------------------------------------
  documents: {
    analyze(text: string, filename?: string, documentTypeHint?: string): Promise<DocumentAnalysisResponse> {
      return request<DocumentAnalysisResponse>("POST", "/documents/analyze", {
        body: { text, filename, document_type_hint: documentTypeHint },
      });
    },

    verify(text: string): Promise<DocumentVerifyResponse> {
      return request<DocumentVerifyResponse>("POST", "/documents/verify", {
        body: { text },
      });
    },

    getTypes(): Promise<{ document_types: string[]; categories: string[] }> {
      return request("GET", "/documents/types");
    },

    uploadAnalyze(file: File, documentTypeHint?: string): Promise<UploadDocumentAnalysisResponse> {
      return uploadRequest<UploadDocumentAnalysisResponse>(
        "/uploads/documents/analyze",
        file,
        documentTypeHint ? { document_type_hint: documentTypeHint } : {},
      );
    },

    uploadVerify(file: File): Promise<UploadDocumentVerifyResponse> {
      return uploadRequest<UploadDocumentVerifyResponse>("/uploads/documents/verify", file);
    },
  },

  // ---------------------------------------------------------------------------
  // Invoices
  // ---------------------------------------------------------------------------
  invoices: {
    process(text: string, invoiceId?: string): Promise<InvoiceProcessResponse> {
      return request<InvoiceProcessResponse>("POST", "/invoices/process", {
        body: { text, invoice_id: invoiceId },
      });
    },

    uploadProcess(file: File, invoiceId?: string): Promise<UploadInvoiceProcessResponse> {
      return uploadRequest<UploadInvoiceProcessResponse>(
        "/uploads/invoices/process",
        file,
        invoiceId ? { invoice_id: invoiceId } : {},
      );
    },

    getDashboard(): Promise<InvoiceDashboard> {
      return request<InvoiceDashboard>("GET", "/invoices/dashboard");
    },

    reconcile(data?: {
      purchase_invoices?: Array<Record<string, unknown>>;
      sales_invoices?: Array<Record<string, unknown>>;
    }): Promise<ReconciliationReport> {
      return request<ReconciliationReport>("POST", "/invoices/reconcile", { body: data || {} });
    },

    export(format = "json"): Promise<Record<string, unknown> | string> {
      return request("GET", `/invoices/export?format=${format}`);
    },
  },

  // ---------------------------------------------------------------------------
  // Verification
  // ---------------------------------------------------------------------------
  verify: {
    ntn(ntn: string): Promise<VerificationResponse> {
      return request<VerificationResponse>("POST", "/verify/ntn", { body: { ntn } });
    },

    filer(ntn: string): Promise<VerificationResponse> {
      return request<VerificationResponse>("POST", "/verify/filer", { body: { ntn } });
    },

    vendor(vendorNtn: string): Promise<VerificationResponse> {
      return request<VerificationResponse>("POST", "/verify/vendor", { body: { vendor_ntn: vendorNtn } });
    },

    cnic(cnic: string): Promise<VerificationResponse> {
      return request<VerificationResponse>("POST", "/verify/cnic", { body: { cnic } });
    },

    business(registrationNumber: string, regType = "ntn"): Promise<VerificationResponse> {
      return request<VerificationResponse>("POST", "/verify/business", {
        body: { registration_number: registrationNumber, reg_type: regType },
      });
    },

    checkAtl(ntn: string): Promise<{ ntn: string; on_atl: boolean; filer_status: string; last_return: string }> {
      return request("GET", `/verify/atl/${ntn}`);
    },

    batch(requests: Array<{ type: string; value: string }>): Promise<VerificationResponse[]> {
      return request<VerificationResponse[]>("POST", "/verify/batch", { body: { requests } });
    },
  },

  // ---------------------------------------------------------------------------
  // Business Reports (Report Generate — business workspace)
  // ---------------------------------------------------------------------------
  businessReports: {
    getTypes(): Promise<{ report_types: string[]; default: string; formats: string[] }> {
      return request("GET", "/business/reports/types");
    },

    generate(data: {
      report_type?: string;
      title: string;
      taxpayer_type?: string;
      ntn?: string;
      tax_year?: number;
      include_calendar?: boolean;
      include_filer_status?: boolean;
    }): Promise<BusinessReportResponse> {
      return request<BusinessReportResponse>("POST", "/business/reports/generate", { body: data });
    },
  },

  // ---------------------------------------------------------------------------
  // Vault (persistent per-user document storage)
  // ---------------------------------------------------------------------------
  vault: {
    list(): Promise<{ user_id: string; documents: VaultDocument[]; count: number }> {
      return request("GET", "/vault/documents");
    },

    create(payload: { filename: string; doc_type: string; content?: string; secure?: boolean }): Promise<VaultDocument> {
      return request("POST", "/vault/documents", { body: payload });
    },

    get(docId: string): Promise<VaultDocument> {
      return request("GET", `/vault/documents/${encodeURIComponent(docId)}`);
    },

    update(docId: string, payload: { filename?: string; doc_type?: string; content?: string }): Promise<VaultDocument> {
      return request("PATCH", `/vault/documents/${encodeURIComponent(docId)}`, { body: payload });
    },

    remove(docId: string): Promise<{ deleted: boolean; id: string }> {
      return request("DELETE", `/vault/documents/${encodeURIComponent(docId)}`);
    },
  },

  // ---------------------------------------------------------------------------
  // Monitor
  // ---------------------------------------------------------------------------
  monitor: {
    subscribe(data: {
      user_id: string;
      ntn: string;
      check_interval_minutes?: number;
      notification_email?: string;
      notification_webhook?: string;
    }): Promise<Record<string, unknown>> {
      return request("POST", "/monitor/subscribe", { body: data });
    },

    unsubscribe(userId: string): Promise<{ user_id: string; unsubscribed: boolean }> {
      return request("DELETE", `/monitor/unsubscribe/${userId}`);
    },

    getDashboard(userId: string): Promise<MonitorDashboard> {
      return request<MonitorDashboard>("GET", `/monitor/dashboard/${userId}`);
    },

    getEvent(eventId: string): Promise<Record<string, unknown>> {
      return request("GET", `/monitor/event/${eventId}`);
    },

    acknowledgeEvent(eventId: string): Promise<{ event_id: string; status: string }> {
      return request("POST", `/monitor/event/${eventId}/acknowledge`);
    },

    resolveEvent(eventId: string): Promise<{ event_id: string; status: string }> {
      return request("POST", `/monitor/event/${eventId}/resolve`);
    },

    getEventTypes(): Promise<{ event_types: string[]; severities: string[] }> {
      return request("GET", "/monitor/event-types");
    },

    /** Simulate a new FBR notice (demo/testing) — event lands in the inbox. */
    simulateNotice(data: {
      ntn: string;
      notice_number: string;
      title: string;
      description: string;
      action_deadline?: string;
    }): Promise<Record<string, unknown>> {
      return request("POST", "/monitor/simulate/notice", { body: data });
    },
  },

  // ---------------------------------------------------------------------------
  // Team
  // ---------------------------------------------------------------------------
  team: {
    register(data: {
      email: string;
      password: string;
      name: string;
      role?: string;
      ntn?: string;
      cnic?: string;
      organization?: string;
      phone?: string;
    }): Promise<Record<string, unknown>> {
      return request("POST", "/team/register", { body: data });
    },

    login(email: string, password: string): Promise<Record<string, unknown>> {
      return request("POST", "/team/login", { body: { email, password } });
    },

    logout(token: string): Promise<{ success: boolean }> {
      return request("POST", "/team/logout", { body: { token } });
    },

    getRoles(): Promise<Record<string, unknown>> {
      return request("GET", "/team/roles");
    },

    getTeamDashboard(teamId: string): Promise<TeamDashboard> {
      return request<TeamDashboard>("GET", `/team/dashboard/${teamId}`);
    },

    getUserDashboard(userId: string): Promise<UserDashboard> {
      return request<UserDashboard>("GET", `/team/user-dashboard/${userId}`);
    },
  },

  // ---------------------------------------------------------------------------
  // Workspaces
  // ---------------------------------------------------------------------------
  workspaces: {
    get(userId: string): Promise<{ user_id: string; workspaces: Team[] }> {
      return request("GET", `/workspaces/${userId}`);
    },

    getHealth(): Promise<{ status: string; service: string; version: string }> {
      return request("GET", "/workspaces/health");
    },

    /** Create a personal or business workspace (a real team under the hood). */
    createWorkspace(data: {
      user_id: string;
      name: string;
      workspace_type: "personal" | "business";
      ntn?: string;
      description?: string;
    }): Promise<{ workspace_id: string; name: string; type: string; created_at?: string }> {
      return request("POST", "/workspaces/create", { body: data });
    },
  },
};
