import { useState } from 'react'

type SystemStatus = 'CONNECTED' | 'READY' | 'ATTENTION'

type ERPSystem = {
  name: string
  system: string
  status: SystemStatus
  materials: string
  lastSync: string
  pending: number
}

const systems: ERPSystem[] = [
  {
    name: 'IOCL',
    system: 'SAP ERP',
    status: 'READY',
    materials: '12,842',
    lastSync: '06 Sep 2026, 18:42',
    pending: 84,
  },
  {
    name: 'ONGC',
    system: 'SAP ERP',
    status: 'READY',
    materials: '9,614',
    lastSync: '06 Sep 2026, 18:31',
    pending: 61,
  },
  {
    name: 'BPCL',
    system: 'Demo ERP Connector',
    status: 'CONNECTED',
    materials: '7,426',
    lastSync: '06 Sep 2026, 18:25',
    pending: 43,
  },
  {
    name: 'NTPC',
    system: 'SAP ERP',
    status: 'ATTENTION',
    materials: '8,391',
    lastSync: '06 Sep 2026, 16:12',
    pending: 78,
  },
]

const exportRows = [
  {
    cpse: 'IOCL',
    code: '10003741',
    nmc: 'MIRA-VAL-000001',
    status: 'APPROVED',
  },
  {
    cpse: 'ONGC',
    code: 'VAL-00921',
    nmc: 'MIRA-VAL-000001',
    status: 'APPROVED',
  },
  {
    cpse: 'BPCL',
    code: 'BV-004821',
    nmc: 'MIRA-VAL-000001',
    status: 'APPROVED',
  },
  {
    cpse: 'NTPC',
    code: 'NT-VAL-1842',
    nmc: 'MIRA-VAL-000002',
    status: 'APPROVED',
  },
  {
    cpse: 'BHEL',
    code: 'BH-VAL-7712',
    nmc: 'MIRA-VAL-000002',
    status: 'APPROVED',
  },
]

function StatusBadge({ status }: { status: SystemStatus }) {
  const labels = {
    CONNECTED: 'Connected',
    READY: 'Adapter Ready',
    ATTENTION: 'Attention',
  }

  return (
    <span className={`erp-status erp-status-${status.toLowerCase()}`}>
      <span className="erp-status-dot" />
      {labels[status]}
    </span>
  )
}

export default function ERPIntegration() {
  const [syncing, setSyncing] = useState(false)
  const [lastAction, setLastAction] = useState('')

  const handleSync = () => {
    setSyncing(true)
    setLastAction('Synchronization initiated')

    window.setTimeout(() => {
      setSyncing(false)
      setLastAction('Demo synchronization completed')
    }, 1200)
  }

  const handleExport = () => {
    setLastAction('Approved mapping export prepared')
  }

  return (
    <div className="page">
      <div className="page-header erp-page-header">
        <div>
          <div className="eyebrow">ENTERPRISE CONNECTIVITY</div>
          <h1>ERP Integration</h1>
          <p>
            Connect CPSE material masters and exchange approved harmonization
            mappings with ERP systems.
          </p>
        </div>

        <div className="erp-environment-badge">
          <span />
          Integration adapters ready
        </div>
      </div>

      <div className="erp-notice">
        <div className="erp-notice-icon">i</div>
        <div>
          <strong>Integration-ready architecture</strong>
          <p>
            MIRA uses an adapter layer so SAP and other ERP systems can be
            connected without changing the harmonization workflow. The
            connectors shown here are demonstration states until a live ERP
            endpoint is configured.
          </p>
        </div>
      </div>

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">SOURCE SYSTEMS</div>
            <h2>Connected Systems</h2>
          </div>

          <span className="erp-system-count">
            {systems.length} systems configured
          </span>
        </div>

        <div className="erp-system-grid">
          {systems.map((system) => (
            <div className="erp-system-card" key={system.name}>
              <div className="erp-system-top">
                <div className="erp-system-logo">
                  {system.name.charAt(0)}
                </div>

                <StatusBadge status={system.status} />
              </div>

              <div className="erp-system-name">{system.name}</div>
              <div className="erp-system-type">{system.system}</div>

              <div className="erp-system-stats">
                <div>
                  <span>Material records</span>
                  <strong>{system.materials}</strong>
                </div>

                <div>
                  <span>Pending sync</span>
                  <strong>{system.pending}</strong>
                </div>
              </div>

              <div className="erp-system-sync">
                <span>Last synchronization</span>
                <strong>{system.lastSync}</strong>
              </div>

              <button
                className="erp-system-button"
                onClick={() => {
                  setLastAction(`${system.name} sync requested`)
                }}
              >
                View Connector
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">DATA EXCHANGE</div>
            <h2>Synchronization</h2>
            <p>
              Exchange material master data through configured ERP adapters.
            </p>
          </div>

          <button
            className="erp-primary-button"
            onClick={handleSync}
            disabled={syncing}
          >
            {syncing ? 'Synchronizing...' : 'Sync Material Masters'}
          </button>
        </div>

        <div className="erp-sync-panel">
          <div className="erp-sync-status">
            <div className="erp-sync-indicator">
              <span />
            </div>

            <div>
              <strong>
                {syncing
                  ? 'Synchronization in progress'
                  : 'Ready for synchronization'}
              </strong>
              <p>
                {lastAction ||
                  'No synchronization is currently running.'}
              </p>
            </div>
          </div>

          <div className="erp-sync-metrics">
            <div>
              <span>Records pending</span>
              <strong>326</strong>
            </div>

            <div>
              <span>Last successful sync</span>
              <strong>06 Sep 2026</strong>
            </div>

            <div>
              <span>Approved mappings</span>
              <strong>7</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">APPROVED OUTPUT</div>
            <h2>Mapping Export</h2>
            <p>
              Export approved CPSE-to-common material mappings for downstream
              ERP processing.
            </p>
          </div>

          <button
            className="erp-secondary-button"
            onClick={handleExport}
          >
            Prepare Export
          </button>
        </div>

        <div className="erp-export-card">
          <table className="erp-export-table">
            <thead>
              <tr>
                <th>CPSE</th>
                <th>Original Material Code</th>
                <th>Common National Code</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {exportRows.map((row) => (
                <tr key={`${row.cpse}-${row.code}`}>
                  <td>
                    <strong>{row.cpse}</strong>
                  </td>

                  <td>
                    <span className="erp-code">{row.code}</span>
                  </td>

                  <td>
                    <span className="erp-nmc">{row.nmc}</span>
                  </td>

                  <td>
                    <span className="erp-approved">
                      Approved
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="erp-export-footer">
            <span>
              Only approved mappings are eligible for export.
            </span>

            <span>{exportRows.length} records ready</span>
          </div>
        </div>
      </section>
    </div>
  )
}
