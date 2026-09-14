import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/shell/AppShell";
import { RequireAuth } from "@/components/shell/RequireAuth";
import { Loading } from "@/components/shell/Loading";
import { LoginPage } from "@/pages/auth/LoginPage";
import { SignupPage } from "@/pages/auth/SignupPage";
import { AuthCallbackPage } from "@/pages/auth/AuthCallbackPage";
import { LandingPage } from "@/pages/LandingPage";

const OverviewPage = lazy(() => import("@/pages/personal/OverviewPage").then((m) => ({ default: m.OverviewPage })));
const AssistantPage = lazy(() => import("@/pages/personal/AssistantPage").then((m) => ({ default: m.AssistantPage })));
const CalculatorPage = lazy(() => import("@/pages/personal/CalculatorPage").then((m) => ({ default: m.CalculatorPage })));
const TaxReducerPage = lazy(() => import("@/pages/personal/TaxReducerPage").then((m) => ({ default: m.TaxReducerPage })));
const InvoicesPage = lazy(() => import("@/pages/personal/InvoicesPage").then((m) => ({ default: m.InvoicesPage })));
const DocumentsPage = lazy(() => import("@/pages/personal/DocumentsPage").then((m) => ({ default: m.DocumentsPage })));
const NoticesPage = lazy(() => import("@/pages/personal/NoticesPage").then((m) => ({ default: m.NoticesPage })));
const CalendarPage = lazy(() => import("@/pages/personal/CalendarPage").then((m) => ({ default: m.CalendarPage })));
const ReadinessPage = lazy(() => import("@/pages/personal/ReadinessPage").then((m) => ({ default: m.ReadinessPage })));
const HealthPage = lazy(() => import("@/pages/personal/HealthPage").then((m) => ({ default: m.HealthPage })));
const VerificationPage = lazy(() => import("@/pages/personal/VerificationPage").then((m) => ({ default: m.VerificationPage })));
const VaultPage = lazy(() => import("@/pages/personal/VaultPage").then((m) => ({ default: m.VaultPage })));
const ResearchPage = lazy(() => import("@/pages/personal/ResearchPage").then((m) => ({ default: m.ResearchPage })));
const SettingsPage = lazy(() => import("@/pages/personal/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const InboxPage = lazy(() => import("@/pages/personal/InboxPage").then((m) => ({ default: m.InboxPage })));
const SubordinatesPage = lazy(() => import("@/pages/personal/SubordinatesPage").then((m) => ({ default: m.SubordinatesPage })));
const WorkspacesPage = lazy(() => import("@/pages/personal/WorkspacesPage").then((m) => ({ default: m.WorkspacesPage })));
const BusinessOverviewPage = lazy(() => import("@/pages/business/BusinessOverviewPage").then((m) => ({ default: m.BusinessOverviewPage })));
const BusinessAssistantPage = lazy(() => import("@/pages/business/BusinessAssistantPage").then((m) => ({ default: m.BusinessAssistantPage })));
const BusinessCalculatorPage = lazy(() => import("@/pages/business/BusinessCalculatorPage").then((m) => ({ default: m.BusinessCalculatorPage })));
const BusinessTaxReducerPage = lazy(() => import("@/pages/business/BusinessTaxReducerPage").then((m) => ({ default: m.BusinessTaxReducerPage })));
const BusinessInvoicesPage = lazy(() => import("@/pages/business/BusinessInvoicesPage").then((m) => ({ default: m.BusinessInvoicesPage })));
const BusinessDocumentsPage = lazy(() => import("@/pages/business/BusinessDocumentsPage").then((m) => ({ default: m.BusinessDocumentsPage })));
const BusinessNoticesPage = lazy(() => import("@/pages/business/BusinessNoticesPage").then((m) => ({ default: m.BusinessNoticesPage })));
const BusinessCalendarPage = lazy(() => import("@/pages/business/BusinessCalendarPage").then((m) => ({ default: m.BusinessCalendarPage })));
const BusinessReadinessPage = lazy(() => import("@/pages/business/BusinessReadinessPage").then((m) => ({ default: m.BusinessReadinessPage })));
const BusinessHealthPage = lazy(() => import("@/pages/business/BusinessHealthPage").then((m) => ({ default: m.BusinessHealthPage })));
const BusinessVerificationPage = lazy(() => import("@/pages/business/BusinessVerificationPage").then((m) => ({ default: m.BusinessVerificationPage })));
const BusinessVaultPage = lazy(() => import("@/pages/business/BusinessVaultPage").then((m) => ({ default: m.BusinessVaultPage })));
const BusinessTeamPage = lazy(() => import("@/pages/business/BusinessTeamPage").then((m) => ({ default: m.BusinessTeamPage })));
const BusinessMonitorPage = lazy(() => import("@/pages/business/BusinessMonitorPage").then((m) => ({ default: m.BusinessMonitorPage })));

export function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Loading label="Loading…" testId="route-loading" />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route
            path="/personal"
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<OverviewPage />} />
            <Route path="overview" element={<OverviewPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="calculator" element={<CalculatorPage />} />
            <Route path="tax-reducer" element={<TaxReducerPage />} />
            <Route path="invoices" element={<InvoicesPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="notices" element={<NoticesPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="readiness" element={<ReadinessPage />} />
            <Route path="health" element={<HealthPage />} />
            <Route path="verification" element={<VerificationPage />} />
            <Route path="vault" element={<VaultPage />} />
            <Route path="research" element={<ResearchPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="inbox" element={<InboxPage />} />
            <Route path="subordinates" element={<SubordinatesPage />} />
            <Route path="workspaces" element={<WorkspacesPage />} />
          </Route>
          <Route
            path="/business"
            element={
              <RequireAuth>
                <AppShell variant="business" />
              </RequireAuth>
            }
          >
            <Route index element={<BusinessOverviewPage />} />
            <Route path="overview" element={<BusinessOverviewPage />} />
            <Route path="assistant" element={<BusinessAssistantPage />} />
            <Route path="calculator" element={<BusinessCalculatorPage />} />
            <Route path="tax-reducer" element={<BusinessTaxReducerPage />} />
            <Route path="invoices" element={<BusinessInvoicesPage />} />
            <Route path="documents" element={<BusinessDocumentsPage />} />
            <Route path="notices" element={<BusinessNoticesPage />} />
            <Route path="calendar" element={<BusinessCalendarPage />} />
            <Route path="readiness" element={<BusinessReadinessPage />} />
            <Route path="health" element={<BusinessHealthPage />} />
            <Route path="verification" element={<BusinessVerificationPage />} />
            <Route path="vault" element={<BusinessVaultPage />} />
            <Route path="team" element={<BusinessTeamPage />} />
            <Route path="monitor" element={<BusinessMonitorPage />} />
          </Route>
          <Route path="*" element={<LandingPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
