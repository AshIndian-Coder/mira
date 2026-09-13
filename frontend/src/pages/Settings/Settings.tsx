import { CheckCircle2, CircleOff } from 'lucide-react'

export default function Settings() {
  return (
    <div className="page">
      <div className="page-header settings-header">
        <div>
          <div className="eyebrow">SYSTEM CONFIGURATION</div>
          <h1>Settings</h1>
          <p>
            Review MIRA governance, matching and integration configuration.
          </p>
        </div>
      </div>

      <div className="settings-layout">
        <main className="settings-main">
          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>Data Steward Profile</h2>
                <p>Current prototype operator context.</p>
              </div>
            </div>

            <div className="settings-grid">
              <div className="settings-field">
                <label>Name</label>
                <div className="settings-value">Data Steward</div>
              </div>

              <div className="settings-field">
                <label>Role</label>
                <div className="settings-value">Master Data Steward</div>
              </div>

              <div className="settings-field">
                <label>Access level</label>
                <div className="settings-value">Governance & Review</div>
              </div>

              <div className="settings-field">
                <label>Environment</label>
                <div className="settings-value">
                  <span className="status-dot" />
                  Prototype Environment
                </div>
              </div>
            </div>
          </section>

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
              title="Audit trail"
              description="Material decisions and governance actions are recorded by the backend audit service."
              enabled
            />

            <CapabilityRow
              title="Steward notifications"
              description="Dedicated notification delivery is not configured in the current prototype."
              enabled={false}
            />
          </section>

          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>System Preferences</h2>
                <p>Application capabilities available in this prototype.</p>
              </div>
            </div>

            <CapabilityRow
              title="Automatic data refresh"
              description="Automatic background refresh is not configured; workspace pages load current data when opened or refreshed."
              enabled={false}
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
            <InfoRow label="Integration" value="Integration ready" />
          </section>

          <section className="settings-card environment-card">
            <div className="environment-indicator">
              <span className="status-dot" />
              <strong>Prototype Environment</strong>
            </div>

            <p>
              MIRA currently supports material ingestion, candidate matching,
              human review, harmonization mappings, audit tracking and mapping
              export. Live ERP/SAP synchronization and production user
              management are not configured in this prototype.
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
