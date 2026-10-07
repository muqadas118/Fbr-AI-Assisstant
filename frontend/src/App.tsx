import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/shell/AppShell";
import { RequireAuth } from "@/components/shell/RequireAuth";
import { Loading } from "@/components/shell/Loading";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { SignupPage } from "@/pages/auth/SignupPage";
import { AuthCallbackPage } from "@/pages/auth/AuthCallbackPage";
import { OnboardingFlow } from "@/components/auth/OnboardingFlow";

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
const BusinessSettingsPage = lazy(() => import("@/pages/business/BusinessSettingsPage").then((m) => ({ default: m.BusinessSettingsPage })));
// Workspace-parity features: business reuses the (workspace-agnostic) personal
// pages so both workspaces expose the same capabilities; business additionally
// has Team + Compliance Monitor.
const BusinessResearchPage = lazy(() => import("@/pages/personal/ResearchPage").then((m) => ({ default: m.ResearchPage })));
// Workspace Hub: Inbox + Subordinates + Workspaces as internal tabs of ONE
// sidebar entry, shared by both workspaces.
const PersonalWorkspaceHubPage = lazy(() => import("@/pages/workspace/WorkspaceHubPage").then((m) => ({ default: m.WorkspaceHubPage })));
const BusinessWorkspaceHubPage = lazy(() => import("@/pages/workspace/WorkspaceHubPage").then((m) => ({ default: m.WorkspaceHubPage })));

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
            path="/onboarding"
            element={
              <RequireAuth>
                <OnboardingFlow />
              </RequireAuth>
            }
          />
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
            <Route path="workspace" element={<PersonalWorkspaceHubPage />} />
            {/* Legacy flat routes → hub (tab carried over). */}
            <Route path="inbox" element={<Navigate to="/personal/workspace?tab=inbox" replace />} />
            <Route path="subordinates" element={<Navigate to="/personal/workspace?tab=subordinates" replace />} />
            <Route path="workspaces" element={<Navigate to="/personal/workspace?tab=workspaces" replace />} />
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
            <Route path="research" element={<BusinessResearchPage />} />
            <Route path="team" element={<BusinessTeamPage />} />
            <Route path="monitor" element={<BusinessMonitorPage />} />
            <Route path="workspace" element={<BusinessWorkspaceHubPage />} />
            {/* Legacy flat routes → hub (tab carried over). */}
            <Route path="inbox" element={<Navigate to="/business/workspace?tab=inbox" replace />} />
            <Route path="subordinates" element={<Navigate to="/business/workspace?tab=subordinates" replace />} />
            <Route path="workspaces" element={<Navigate to="/business/workspace?tab=workspaces" replace />} />
            <Route path="settings" element={<BusinessSettingsPage />} />
          </Route>
          <Route path="*" element={<LandingPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
