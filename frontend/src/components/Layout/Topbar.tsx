import { LogOut } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

function getRoleLabel(role?: string): string {
  switch (role) {
    case 'admin':
      return 'Administrator'
    case 'data_steward':
      return 'Data Steward'
    case 'reviewer':
      return 'Reviewer'
    case 'auditor':
      return 'Auditor'
    default:
      return role || 'Operator'
  }
}

function getInitials(name?: string | null, email?: string): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
    }
    return name.slice(0, 2).toUpperCase()
  }
  if (email) {
    return email.slice(0, 2).toUpperCase()
  }
  return 'MI'
}

function Topbar() {
  const { user, logout } = useAuth()

  const displayName = user?.full_name || user?.email || 'User'
  const roleLabel = getRoleLabel(user?.role)
  const initials = getInitials(user?.full_name, user?.email)

  return (
    <header className="topbar">
      <div>
        <span className="topbar-context">NATIONAL MATERIAL MASTER</span>
      </div>

      <div className="user-area">
        <div className="user-info-text">
          <span className="user-name">{displayName}</span>
          <span className="user-role-badge">{roleLabel}</span>
        </div>

        <div className="avatar" title={`${displayName} (${roleLabel})`}>
          {initials}
        </div>

        <button
          type="button"
          onClick={() => logout()}
          className="logout-btn"
          title="Sign out of MIRA"
        >
          <LogOut size={14} />
          <span>Logout</span>
        </button>
      </div>
    </header>
  )
}

export default Topbar
