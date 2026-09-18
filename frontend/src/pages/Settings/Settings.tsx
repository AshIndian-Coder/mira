import { CheckCircle2, CircleOff, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

function formatRoleName(role?: string): string {
  switch (role) {
    case 'admin':
      return 'System Administrator'
    case 'data_steward':
      return 'Master Data Steward'
    case 'reviewer':
      return 'Technical Reviewer'
    case 'auditor':
      return 'Governance Auditor'
    default:
      return role || 'Operator'
  }
}

function getAccessLevelDescription(role?: string): string {
  switch (role) {
    case 'admin':
      return 'Full Administrative & User Management Access'
    case 'data_steward':
      return 'Ingestion, Harmonization & Mapping Access'
    case 'reviewer':
      return 'Match Review & Validation Access'
    case 'auditor':
      return 'Governance & Audit Trail Inspection Access'
    default:
      return 'Standard Access'
  }
}

export default function Settings() {
  const { user, isAdmin } = useAuth()

  return (
    <div className="page">
      <div className="page-header settings-header">
        <div>
          <div className="eyebrow">SYSTEM CONFIGURATION</div>
          <h1>Settings</h1>
          <p>
            Review MIRA governance, security credentials, and matching configuration.
          </p>
        </div>
      </div>

      <div className="settings-layout">
        <main className="settings-main">
          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>Authenticated User Profile</h2>
                <p>Current active session identity and authorization scope.</p>
              </div>
            </div>

            <div className="settings-grid">
              <div className="settings-field">
                <label>Name</label>
                <div className="settings-value">{user?.full_name || 'System Operator'}</div>
              </div>

              <div className="settings-field">
                <label>Official Email</label>
                <div className="settings-value">{user?.email || '—'}</div>
              </div>

              <div className="settings-field">
                <label>Role</label>
                <div className="settings-value">{formatRoleName(user?.role)}</div>
              </div>

              <div className="settings-field">
                <label>Access level</label>
                <div className="settings-value">{getAccessLevelDescription(user?.role)}</div>
              </div>

              <div className="settings-field">
                <label>Assigned CPSE</label>
                <div className="settings-value">
                  {user?.cpse_short_code || 'All CPSEs (National Level)'}
                </div>
              </div>

              <div className="settings-field">
                <label>Account Status</label>
                <div className="settings-value">
                  <span className="status-dot" />
                  {user?.is_active ? 'Active & Authorized' : 'Suspended'}
                </div>
              </div>
            </div>
          </section>

          {isAdmin && (
            <section className="settings-card">
              <div className="settings-card-header">
                <div>
                  <h2>User Administration</h2>
                  <p>Provision and configure CPSE access roles.</p>
                </div>
                <Link
                  to="/users"
                  className="user-action-btn edit-btn"
                  style={{ padding: '6px 12px', textDecoration: 'none' }}
                >
                  <Users size={14} />
                  <span>Open User Directory</span>
                </Link>
              </div>
              <p style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                You have administrative privileges to provision new accounts, assign CPSE organizational scopes, update access roles, and deactivate personnel.
              </p>
            </section>
          )}

          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>Matching & Harmonization</h2>
                <p>Current capabilities provided by the matching engine.</p>
              </div>
            </div>

            <CapabilityRow
              title="Critical field validation"
              description="Applicable critical specifications are evaluated before a candidate can be treated as high confidence."
              enabled
            />

            <CapabilityRow
              title="Human review for uncertain matches"
              description="Ambiguous or conflicting candidate relationships can be routed through the backend review queue."
              enabled
            />

            <CapabilityRow
              title="Preserve original CPSE codes"
              description="Source-system material codes remain available in common-material and mapping records."
              enabled
            />
          </section>

          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>Governance & Audit</h2>
                <p>Current traceability and operational capabilities.</p>
              </div>
            </div>

            <CapabilityRow
              title="Audit trail & RBAC attribution"
              description="Material decisions and review approvals record real authenticated reviewer identity in audit_logs."
              enabled
            />

            <CapabilityRow
              title="JWT Stateless Authentication"
              description="Secure token-based session handling with role-based API authorization."
              enabled
            />
          </section>
        </main>

        <aside className="settings-side">
          <section className="settings-card system-card">
            <div className="settings-card-header">
              <div>
                <h2>System Information</h2>
                <p>Current MIRA configuration.</p>
              </div>
            </div>

            <InfoRow label="Application" value="MIRA" />
            <InfoRow label="Version" value="0.1.0" />
            <InfoRow label="Material master" value="National" />
            <InfoRow label="Matching engine" value="AI-assisted" />
            <InfoRow label="Database" value="PostgreSQL" />
            <InfoRow label="Auth & RBAC" value="Active (JWT / Bcrypt)" />
          </section>

          <section className="settings-card environment-card">
            <div className="environment-indicator">
              <span className="status-dot" />
              <strong>Enterprise Mode</strong>
            </div>

            <p>
              MIRA enforces role-based access control across material ingestion, candidate matching,
              human review queues, harmonization mappings, and audit tracking.
            </p>
          </section>
        </aside>
      </div>
    </div>
  )
}

function CapabilityRow({
  title,
  description,
  enabled,
}: {
  title: string
  description: string
  enabled: boolean
}) {
  return (
    <div className="setting-row">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>

      <div
        className={`settings-capability ${enabled ? 'enabled' : 'disabled'}`}
        aria-label={enabled ? 'Configured' : 'Not configured'}
      >
        {enabled ? <CheckCircle2 size={17} /> : <CircleOff size={17} />}
        <span>{enabled ? 'Configured' : 'Not configured'}</span>
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
