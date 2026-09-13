import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthProvider } from './lib/AuthContext'
import { GuestCancelPage } from './pages/guest/GuestCancelPage'
import { GuestCheckInPage } from './pages/guest/GuestCheckInPage'
import { GuestStatusPage } from './pages/guest/GuestStatusPage'
import { LoginPage } from './pages/LoginPage'
import { EtaConfigPage } from './pages/manager/EtaConfigPage'
import { EtaRuleFormPage } from './pages/manager/EtaRuleFormPage'
import { GracePeriodFormPage } from './pages/manager/GracePeriodFormPage'
import { ManagerLandingPage } from './pages/manager/ManagerLandingPage'
import { TableConfigFormPage } from './pages/manager/TableConfigFormPage'
import { TableConfigListPage } from './pages/manager/TableConfigListPage'
import { WorkerFormPage } from './pages/manager/WorkerFormPage'
import { WorkerListPage } from './pages/manager/WorkerListPage'
import { StaffLandingPage } from './pages/staff/StaffLandingPage'
import { TableStatusPage } from './pages/staff/TableStatusPage'
import { WaitlistPage } from './pages/staff/WaitlistPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/login" element={<LoginPage />} />

          <Route path="/check-in/:token" element={<GuestCheckInPage />} />
          <Route path="/check-in/status/:publicIdentifier" element={<GuestStatusPage />} />
          <Route path="/check-in/status/:publicIdentifier/cancel" element={<GuestCancelPage />} />

          <Route
            path="/staff"
            element={
              <ProtectedRoute role="staff_or_manager">
                <AppLayout variant="staff" />
              </ProtectedRoute>
            }
          >
            <Route index element={<StaffLandingPage />} />
            <Route path="waitlist" element={<WaitlistPage />} />
            <Route path="tables" element={<TableStatusPage />} />
          </Route>

          <Route
            path="/manager"
            element={
              <ProtectedRoute role="manager">
                <AppLayout variant="manager" />
              </ProtectedRoute>
            }
          >
            <Route index element={<ManagerLandingPage />} />
            <Route path="workers" element={<WorkerListPage />} />
            <Route path="workers/new" element={<WorkerFormPage />} />
            <Route path="workers/:userId" element={<WorkerFormPage />} />
            <Route path="tables" element={<TableConfigListPage />} />
            <Route path="tables/new" element={<TableConfigFormPage />} />
            <Route path="tables/:tableId" element={<TableConfigFormPage />} />
            <Route path="eta" element={<EtaConfigPage />} />
            <Route path="eta/rules/new" element={<EtaRuleFormPage />} />
            <Route path="eta/rules/:ruleId" element={<EtaRuleFormPage />} />
            <Route path="eta/grace-period" element={<GracePeriodFormPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
