import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/shell/AppShell";
import { OverviewPage } from "@/pages/personal/OverviewPage";
import { AssistantPage } from "@/pages/personal/AssistantPage";
import { CalculatorPage } from "@/pages/personal/CalculatorPage";
import { TaxReducerPage } from "@/pages/personal/TaxReducerPage";
import { InvoicesPage } from "@/pages/personal/InvoicesPage";
import { DocumentsPage } from "@/pages/personal/DocumentsPage";
import { NoticesPage } from "@/pages/personal/NoticesPage";
import { CalendarPage } from "@/pages/personal/CalendarPage";
import { ReadinessPage } from "@/pages/personal/ReadinessPage";
import { HealthPage } from "@/pages/personal/HealthPage";
import { VerificationPage } from "@/pages/personal/VerificationPage";
import { VaultPage } from "@/pages/personal/VaultPage";
import { ResearchPage } from "@/pages/personal/ResearchPage";
import { SettingsPage } from "@/pages/personal/SettingsPage";
import { InboxPage } from "@/pages/personal/InboxPage";
import { SubordinatesPage } from "@/pages/personal/SubordinatesPage";
import { WorkspacesPage } from "@/pages/personal/WorkspacesPage";
import { BusinessOverviewPage } from "@/pages/business/BusinessOverviewPage";
import { BusinessAssistantPage } from "@/pages/business/BusinessAssistantPage";
import { BusinessCalculatorPage } from "@/pages/business/BusinessCalculatorPage";
import { BusinessTaxReducerPage } from "@/pages/business/BusinessTaxReducerPage";
import { BusinessInvoicesPage } from "@/pages/business/BusinessInvoicesPage";
import { BusinessDocumentsPage } from "@/pages/business/BusinessDocumentsPage";
import { BusinessNoticesPage } from "@/pages/business/BusinessNoticesPage";
import { BusinessCalendarPage } from "@/pages/business/BusinessCalendarPage";
import { BusinessReadinessPage } from "@/pages/business/BusinessReadinessPage";
import { BusinessHealthPage } from "@/pages/business/BusinessHealthPage";
import { BusinessVerificationPage } from "@/pages/business/BusinessVerificationPage";
import { BusinessVaultPage } from "@/pages/business/BusinessVaultPage";
import { BusinessTeamPage } from "@/pages/business/BusinessTeamPage";
import { BusinessMonitorPage } from "@/pages/business/BusinessMonitorPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/personal/overview" replace />} />
        <Route path="/personal" element={<AppShell />}>
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
        <Route path="/business" element={<AppShell variant="business" />}>
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
        <Route path="*" element={<Navigate to="/personal/overview" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
