import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import type { UserRole } from '../../lib/api'

interface ProtectedRouteProps {
  children: ReactNode
  requiredRole?: UserRole | UserRole[]
}

export default function ProtectedRoute({
  children,
  requiredRole,
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, hasRole } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          height: '100vh',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: '1rem',
          background: 'var(--color-bg, #0b1329)',
          color: 'var(--color-text, #f8fafc)',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <div className="status-dot" style={{ width: '16px', height: '16px' }} />
        <span>Authenticating session…</span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requiredRole && !hasRole(requiredRole)) {
    return (
      <div className="page">
        <div className="mapping-info-banner">
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Access Restricted</strong>
            <p>Your current role does not have authorization to access this workspace module.</p>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
