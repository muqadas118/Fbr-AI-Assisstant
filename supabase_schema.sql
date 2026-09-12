-- =============================================================================
-- FBR AI Tax & Compliance Assistant — Supabase Database Schema
-- Run this in: Supabase Dashboard → SQL Editor
-- =============================================================================

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- Enable Row Level Security (RLS)
-- uncomment after tables are created:
-- alter table profiles enable row level security;
-- alter table calculations enable row level security;
-- alter table invoices enable row level security;
-- ... (same for all tables)


-- =============================================================================
-- 1. PROFILES (extends auth.users)
-- =============================================================================
create table if not exists public.profiles (
    id uuid references auth.users(id) on delete cascade primary key,
    email text,
    full_name text,
    ntn text,
    cnic text,
    phone text,
    organization text,
    role text default 'accountant' check (role in ('admin', 'manager', 'accountant', 'viewer')),
    avatar_url text,
    timezone text default 'Asia/Karachi',
    email_verified boolean default false,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

alter table public.profiles enable row level security;
create policy "Users can view own profile" on public.profiles
    for select using (auth.uid() = id);
create policy "Users can update own profile" on public.profiles
    for update using (auth.uid() = id);

comment on table public.profiles is 'User profile extension — links to auth.users';


-- =============================================================================
-- 2. TAX CALCULATIONS
-- =============================================================================
create table if not exists public.calculations (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    calc_type text not null check (calc_type in (
        'income_tax', 'sales_tax', 'withholding_tax', 'federal_excise',
        'capital_gains', 'property_tax', 'dividend_tax', 'customs_duty',
        'business_tax', 'advance_tax', 'salary_tax'
    )),
    inputs jsonb not null default '{}',
    result jsonb not null default '{}',
    tax_year text,
    fiscal_year text,
    amount_pkruah text,
    audit_id text,
    created_at timestamptz default now()
);

alter table public.calculations enable row level security;
create policy "Users can CRUD own calculations" on public.calculations
    for all using (auth.uid() = user_id);
create policy "Users can view own calculations" on public.calculations
    for select using (auth.uid() = user_id);

create index if not exists idx_calc_user_id on public.calculations(user_id);
create index if not exists idx_calc_type on public.calculations(calc_type);
create index if not exists idx_calc_created on public.calculations(created_at desc);


-- =============================================================================
-- 3. FBR NOTICES
-- =============================================================================
create table if not exists public.notices (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    notice_number text,
    notice_type text,
    section text,
    law text,
    authority text,
    issue_date date,
    reply_deadline date,
    priority text check (priority in ('critical', 'high', 'medium', 'low')),
    status text default 'pending' check (status in ('pending', 'filed', 'resolved', 'escalated')),
    raw_text text,
    extracted_fields jsonb default '{}',
    action_plan jsonb default '[]',
    appeal_info jsonb default '{}',
    grounds jsonb default '[]',
    risk_score integer,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

alter table public.notices enable row level security;
create policy "Users manage own notices" on public.notices
    for all using (auth.uid() = user_id);

create index if not exists idx_notice_user on public.notices(user_id);
create index if not exists idx_notice_deadline on public.notices(reply_deadline);
create index if not exists idx_notice_status on public.notices(status);


-- =============================================================================
-- 4. INVOICES
-- =============================================================================
create table if not exists public.invoices (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    invoice_number text not null,
    vendor_name text,
    vendor_ntn text,
    vendor_cnic text,
    invoice_date date,
    amount_pkruah numeric(18, 2),
    wht_deducted numeric(18, 2),
    wht_deposited numeric(18, 2),
    wht_gap numeric(18, 2) generated always as (wht_deducted - wht_deposited) stored,
    wht_status text default 'pending' check (wht_status in ('valid', 'mismatch', 'pending', 'reconciled')),
    itc_claimed numeric(18, 2),
    itc_admissible numeric(18, 2),
    certificate_number text,
    tax_period text,
    notes text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (user_id, invoice_number)
);

alter table public.invoices enable row level security;
create policy "Users manage own invoices" on public.invoices
    for all using (auth.uid() = user_id);

create index if not exists idx_invoice_user on public.invoices(user_id);
create index if not exists idx_invoice_vendor_ntn on public.invoices(vendor_ntn);
create index if not exists idx_invoice_status on public.invoices(wht_status);


-- =============================================================================
-- 5. DOCUMENTS
-- =============================================================================
create table if not exists public.documents (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    file_name text not null,
    file_type text,
    file_size_bytes bigint,
    storage_path text,
    classification text check (classification in (
        'itr_form', 'form_16a', 'form_16b', 'wealth_statement',
        'cnic_copy', 'fbr_notice', 'contract', 'other'
    )),
    confidence_score numeric(5, 2),
    extracted_fields jsonb default '{}',
    tax_year text,
    status text default 'uploaded' check (status in ('uploaded', 'processing', 'classified', 'review', 'filed')),
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

alter table public.documents enable row level security;
create policy "Users manage own documents" on public.documents
    for all using (auth.uid() = user_id);

create index if not exists idx_doc_user on public.documents(user_id);
create index if not exists idx_doc_class on public.documents(classification);


-- =============================================================================
-- 6. COMPLIANCE EVENTS / CALENDAR
-- =============================================================================
create table if not exists public.compliance_events (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    title text not null,
    description text,
    event_type text check (event_type in (
        'return_filing', 'tax_deposit', 'notice_response', 'audit',
        'advance_tax', 'wht_statement', 'wealth_statement', 'other'
    )),
    due_date date not null,
    amount_pkruah numeric(18, 2),
    section text,
    form_reference text,
    priority text default 'medium' check (priority in ('critical', 'high', 'medium', 'low')),
    status text default 'upcoming' check (status in ('upcoming', 'due', 'filed', 'overdue', 'cancelled')),
    reminder_sent boolean default false,
    reminder_dates text[] default '{}',
    recurrence text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

alter table public.compliance_events enable row level security;
create policy "Users manage own events" on public.compliance_events
    for all using (auth.uid() = user_id);

create index if not exists idx_event_user on public.compliance_events(user_id);
create index if not exists idx_event_due on public.compliance_events(due_date);
create index if not exists idx_event_status on public.compliance_events(status);


-- =============================================================================
-- 7. VERIFICATION LOGS
-- =============================================================================
create table if not exists public.verification_logs (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    lookup_type text check (lookup_type in ('ntn', 'cnic', 'vendor', 'filer_status')),
    lookup_value text not null,
    result_status text,
    filer_status boolean,
    risk_flags text[],
    raw_response jsonb default '{}',
    created_at timestamptz default now()
);

alter table public.verification_logs enable row level security;
create policy "Users view own logs" on public.verification_logs
    for select using (auth.uid() = user_id);
create policy "Users insert logs" on public.verification_logs
    for insert with check (auth.uid() = user_id);

create index if not exists idx_verify_user on public.verification_logs(user_id);
create index if not exists idx_verify_type_val on public.verification_logs(lookup_type, lookup_value);


-- =============================================================================
-- 8. Q&A / CHAT HISTORY
-- =============================================================================
create table if not exists public.chat_history (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    query text not null,
    answer text,
    domains text[],
    primary_domain text,
    sources jsonb default '[]',
    verification jsonb default '{}',
    tokens_used integer,
    latency_ms integer,
    created_at timestamptz default now()
);

alter table public.chat_history enable row level security;
create policy "Users view own history" on public.chat_history
    for select using (auth.uid() = user_id);
create policy "Users insert history" on public.chat_history
    for insert with check (auth.uid() = user_id);

create index if not exists idx_chat_user on public.chat_history(user_id);
create index if not exists idx_chat_created on public.chat_history(created_at desc);


-- =============================================================================
-- 9. TAX HEALTH SCORES
-- =============================================================================
create table if not exists public.tax_health_scores (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    composite_score integer not null check (composite_score between 0 and 100),
    filing_score integer,
    deposit_score integer,
    wht_score integer,
    notice_score integer,
    docs_score integer,
    risk_factors jsonb default '[]',
    penalty_estimate_pkruah numeric(18, 2),
    period text,
    created_at timestamptz default now()
);

alter table public.tax_health_scores enable row level security;
create policy "Users view own scores" on public.tax_health_scores
    for select using (auth.uid() = user_id);
create policy "Users insert scores" on public.tax_health_scores
    for insert with check (auth.uid() = user_id);

create index if not exists idx_health_user on public.tax_health_scores(user_id);
create index if not exists idx_health_created on public.tax_health_scores(created_at desc);


-- =============================================================================
-- 10. AUDIT LOGS
-- =============================================================================
create table if not exists public.audit_logs (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete set null,
    action text not null,
    resource text,
    resource_id text,
    details jsonb default '{}',
    ip_address inet,
    user_agent text,
    created_at timestamptz default now()
);

alter table public.audit_logs enable row level security;
create policy "Admins view all logs" on public.audit_logs
    for select using (
        auth.uid() = user_id or
        exists (select 1 from public.profiles where id = auth.uid() and role = 'admin')
    );
create policy "Authenticated users insert logs" on public.audit_logs
    for insert with check (auth.uid() is not null);

create index if not exists idx_audit_user on public.audit_logs(user_id);
create index if not exists idx_audit_action on public.audit_logs(action);
create index if not exists idx_audit_created on public.audit_logs(created_at desc);


-- =============================================================================
-- 11. API KEYS (user programmatic access)
-- =============================================================================
create table if not exists public.api_keys (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    key_hash text not null,
    name text not null,
    scopes text[] default '{read}',
    last_used_at timestamptz,
    expires_at timestamptz,
    is_active boolean default true,
    created_at timestamptz default now()
);

alter table public.api_keys enable row level security;
create policy "Users manage own keys" on public.api_keys
    for all using (auth.uid() = user_id);

create index if not exists idx_apikey_user on public.api_keys(user_id);
create index if not exists idx_apikey_hash on public.api_keys(key_hash);


-- =============================================================================
-- 12. WEBHOOK SUBSCRIPTIONS (FBR Monitor)
-- =============================================================================
create table if not exists public.webhook_subscriptions (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    subscription_type text not null check (subscription_type in (
        'ntn_notices', 'ntn_orders', 'ntn_intimations',
        'policy_updates', 'sros', 'reminders'
    )),
    target text,
    webhook_url text,
    is_active boolean default true,
    last_event_at timestamptz,
    events_received integer default 0,
    created_at timestamptz default now()
);

alter table public.webhook_subscriptions enable row level security;
create policy "Users manage own subscriptions" on public.webhook_subscriptions
    for all using (auth.uid() = user_id);


-- =============================================================================
-- 13. MONITORING ALERTS
-- =============================================================================
create table if not exists public.alerts (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade,
    title text not null,
    message text,
    severity text check (severity in ('info', 'warning', 'error', 'critical')),
    source text,
    channel text default 'internal' check (channel in ('email', 'sms', 'push', 'webhook', 'internal')),
    metadata jsonb default '{}',
    is_resolved boolean default false,
    acknowledged_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz default now()
);

alter table public.alerts enable row level security;
create policy "Users view own alerts" on public.alerts
    for select using (auth.uid() = user_id or auth.uid() is null);
create policy "Users manage own alerts" on public.alerts
    for update using (auth.uid() = user_id or auth.uid() is null);

create index if not exists idx_alert_user on public.alerts(user_id);
create index if not exists idx_alert_severity on public.alerts(severity);
create index if not exists idx_alert_resolved on public.alerts(is_resolved);


-- =============================================================================
-- 14. USER SESSIONS (for audit / tracking)
-- =============================================================================
create table if not exists public.user_sessions (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade not null,
    ip_address inet,
    user_agent text,
    device_type text,
    location text,
    is_active boolean default true,
    created_at timestamptz default now(),
    expires_at timestamptz
);

alter table public.user_sessions enable row level security;
create policy "Users view own sessions" on public.user_sessions
    for select using (auth.uid() = user_id);
create policy "Users manage own sessions" on public.user_sessions
    for update using (auth.uid() = user_id);


-- =============================================================================
-- TRIGGER: auto-update updated_at
-- =============================================================================
create or replace function public.update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger trg_profiles_updated
    before update on public.profiles
    for each row execute function public.update_updated_at();

create trigger trg_notices_updated
    before update on public.notices
    for each row execute function public.update_updated_at();

create trigger trg_invoices_updated
    before update on public.invoices
    for each row execute function public.update_updated_at();

create trigger trg_documents_updated
    before update on public.documents
    for each row execute function public.update_updated_at();

create trigger trg_compliance_updated
    before update on public.compliance_events
    for each row execute function public.update_updated_at();


-- =============================================================================
-- FUNCTION: auto-create profile on signup
-- =============================================================================
create or replace function public.handle_new_user()
returns trigger as $$
begin
    insert into public.profiles (id, email, full_name, avatar_url)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
        new.raw_user_meta_data->>'avatar_url'
    );
    return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();


-- =============================================================================
-- FUNCTION: log audit events
-- =============================================================================
create or replace function public.log_audit(
    p_action text,
    p_resource text default null,
    p_resource_id text default null,
    p_details jsonb default '{}'
) returns uuid as $$
declare
    v_id uuid;
begin
    insert into public.audit_logs (user_id, action, resource, resource_id, details)
    values (auth.uid(), p_action, p_resource, p_resource_id, p_details)
    returning id into v_id;
    return v_id;
end;
$$ language plpgsql security definer;


-- =============================================================================
-- SEED DATA: sample compliance events (run once)
-- =============================================================================
-- Uncomment below after first user signs up:
/*
insert into public.compliance_events (user_id, title, event_type, due_date, section, priority, status)
values
    (auth.uid(), 'Advance Tax Q1 FY26', 'advance_tax', '2025-09-15', '147', 'high', 'upcoming'),
    (auth.uid(), 'Quarterly WHT Statement', 'wht_statement', '2025-09-30', '165', 'medium', 'upcoming'),
    (auth.uid(), 'Sales Tax Return Sep', 'return_filing', '2025-10-07', 'STR-1', 'medium', 'upcoming'),
    (auth.uid(), 'ITR FY25 Filing', 'return_filing', '2025-12-31', '114', 'critical', 'upcoming');
*/
