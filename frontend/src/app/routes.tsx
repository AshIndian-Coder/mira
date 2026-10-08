import { Routes, Route, Navigate } from 'react-router-dom'

import AppShell from '../components/Layout/AppShell'
import ProtectedRoute from '../components/Auth/ProtectedRoute'
import Login from '../pages/Login/Login'
import Dashboard from '../pages/Dashboard/Dashboard'
import Materials from '../pages/Materials'
import MatchReview from '../pages/MatchReview/MatchReview'
import CommonMaterials from '../pages/CommonMaterials/CommonMaterials'
import Mappings from '../pages/Mappings/Mappings'
import ERPIntegration from '../pages/ERPIntegration/ERPIntegration'
import Analytics from '../pages/Analytics/Analytics'
import AuditTrail from '../pages/AuditTrail/AuditTrail'
import Settings from '../pages/Settings'
import UserManagement from '../pages/UserManagement/UserManagement'

export default function AppRoutes() {
  return (
    <Routes>
      {/* Public Login Route */}
      <Route path="/login" element={<Login />} />

      {/* Protected App Workspace Routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppShell>
              <Navigate to="/dashboard" replace />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <AppShell>
              <Dashboard />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/materials"
        element={
          <ProtectedRoute>
            <AppShell>
              <Materials />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/match-review"
        element={
          <ProtectedRoute>
            <AppShell>
              <MatchReview />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/common-materials"
        element={
          <ProtectedRoute>
            <AppShell>
              <CommonMaterials />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/mappings"
        element={
          <ProtectedRoute>
            <AppShell>
              <Mappings />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/erp-integration"
        element={
          <ProtectedRoute>
            <AppShell>
              <ERPIntegration />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/analytics"
        element={
          <ProtectedRoute>
            <AppShell>
              <Analytics />
            </AppShell>
          </ProtectedRoute>
        }
      />

      {/* view_audit is admin, data_steward and auditor only — reviewers are excluded. */}
      <Route
        path="/audit-trail"
        element={
          <ProtectedRoute requiredRole={['admin', 'data_steward', 'auditor']}>
            <AppShell>
              <AuditTrail />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/users"
        element={
          <ProtectedRoute requiredRole="admin">
            <AppShell>
              <UserManagement />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <AppShell>
              <Settings />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}