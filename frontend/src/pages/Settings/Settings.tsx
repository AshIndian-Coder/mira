import { useState } from 'react'
import { Check, RotateCcw, Save } from 'lucide-react'

export default function Settings() {
  const [saved, setSaved] = useState(false)

  const [settings, setSettings] = useState({
    autoRefresh: true,
    requireReview: true,
    preserveSourceCodes: true,
    criticalFieldGate: true,
    auditLogging: true,
    notifications: true,
  })

  const toggle = (key: keyof typeof settings) => {
    setSettings((current) => ({
      ...current,
      [key]: !current[key],
    }))
    setSaved(false)
  }

  const saveSettings = () => {
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2500)
  }

  const resetSettings = () => {
    setSettings({
      autoRefresh: true,
      requireReview: true,
      preserveSourceCodes: true,
      criticalFieldGate: true,
      auditLogging: true,
      notifications: true,
    })
    setSaved(false)
  }

  return (
    <div className="page">
      <div className="page-header settings-header">
        <div>
          <div className="eyebrow">SYSTEM CONFIGURATION</div>
          <h1>Settings</h1>
          <p>
            Configure MIRA governance, matching and integration preferences.
          </p>
        </div>
      </div>

      <div className="settings-layout">
        <main className="settings-main">

          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>Data Steward Profile</h2>
                <p>Current user and governance role.</p>
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
                <p>Rules controlling automated material processing.</p>
              </div>
            </div>

            <SettingRow
              title="Critical field validation"
              description="Require applicable critical specifications to pass before a material can be treated as high confidence."
              checked={settings.criticalFieldGate}
              onChange={() => toggle('criticalFieldGate')}
            />

            <SettingRow
              title="Human review for uncertain matches"
              description="Route ambiguous or conflicting candidate matches to the review queue."
              checked={settings.requireReview}
              onChange={() => toggle('requireReview')}
            />

            <SettingRow
              title="Preserve original CPSE codes"
              description="Keep source-system material identities when creating common material mappings."
              checked={settings.preserveSourceCodes}
              onChange={() => toggle('preserveSourceCodes')}
            />
          </section>

          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>Governance & Audit</h2>
                <p>Controls for traceability and operational oversight.</p>
              </div>
            </div>

            <SettingRow
              title="Audit trail"
              description="Record material decisions, approvals, mappings and governance actions."
              checked={settings.auditLogging}
              onChange={() => toggle('auditLogging')}
            />

            <SettingRow
              title="Steward notifications"
              description="Show notifications for pending reviews and governance actions."
              checked={settings.notifications}
              onChange={() => toggle('notifications')}
            />
          </section>

          <section className="settings-card">
            <div className="settings-card-header">
              <div>
                <h2>System Preferences</h2>
                <p>General application behaviour.</p>
              </div>
            </div>

            <SettingRow
              title="Automatic data refresh"
              description="Refresh dashboard and workspace statistics when updated data is available."
              checked={settings.autoRefresh}
              onChange={() => toggle('autoRefresh')}
            />
          </section>

          <div className="settings-actions">
            <button className="secondary-button" onClick={resetSettings}>
              <RotateCcw size={15} />
              Reset
            </button>

            <button className="primary-button" onClick={saveSettings}>
              {saved ? <Check size={15} /> : <Save size={15} />}
              {saved ? 'Saved' : 'Save Changes'}
            </button>
          </div>
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
            <InfoRow label="Integration" value="Adapter ready" />
          </section>

          <section className="settings-card environment-card">
            <div className="environment-indicator">
              <span className="status-dot" />
              <strong>Prototype Environment</strong>
            </div>

            <p>
              MIRA is currently running in prototype mode. Production ERP
              endpoints can be configured through the integration layer.
            </p>
          </section>
        </aside>
      </div>
    </div>
  )
}

function SettingRow({
  title,
  description,
  checked,
  onChange,
}: {
  title: string
  description: string
  checked: boolean
  onChange: () => void
}) {
  return (
    <div className="setting-row">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>

      <button
        type="button"
        className={`toggle ${checked ? 'active' : ''}`}
        onClick={onChange}
        aria-pressed={checked}
      >
        <span />
      </button>
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
