import { useEffect, useState } from 'react'

import { api, formatNumber } from '../../lib/api'

type ExportRow = {
  cpse: string
  code: string
  nmc: string
  status: string
}

type CpseSystem = {
  name: string
  materials: number
  pending: number
}

export default function ERPIntegration() {
  const [systems, setSystems] = useState<CpseSystem[]>([])
  const [exportRows, setExportRows] = useState<ExportRow[]>([])
  const [pendingReview, setPendingReview] = useState(0)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [lastAction, setLastAction] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const [cpseRes, overview, exportRes] = await Promise.all([
          api.analyticsByCpse(),
          api.analyticsOverview(),
          api.exportMappingsFlat(),
        ])

        setSystems(
          cpseRes.cpse_breakdown.map((row) => ({
            name: row.cpse,
            materials: row.material_count,
            pending: row.candidate_pair_involvements,
          })),
        )
        setPendingReview(overview.review_pending)
        setExportRows(
          exportRes.rows.map((row) => ({
            cpse: row.cpse,
            code: row.cpse_material_code,
            nmc: row.nmc,
            status: 'APPROVED',
          })),
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load ERP data')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const handleSync = () => {
    setSyncing(true)
    setLastAction('Synchronization initiated')
    window.setTimeout(() => {
      setSyncing(false)
      setLastAction('Material master sync completed (adapter demo)')
    }, 1200)
  }

  const handleExport = async () => {
    try {
      const result = await api.exportMappingsFlat()
      const blob = new Blob([JSON.stringify(result.rows, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'mira-erp-export.json'
      link.click()
      URL.revokeObjectURL(url)
      setLastAction(`Prepared ${result.total_rows} approved mapping rows for export`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  return (
    <div className="page">
      <div className="page-header erp-page-header">
        <div>
          <div className="eyebrow">ENTERPRISE CONNECTIVITY</div>
          <h1>ERP Integration</h1>
          <p>Connect CPSE material masters and exchange approved harmonization mappings.</p>
        </div>
      </div>

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Error</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">SOURCE SYSTEMS</div>
            <h2>Connected Systems</h2>
          </div>
          <span className="erp-system-count">
            {loading ? '…' : `${systems.length} CPSE sources ingested`}
          </span>
        </div>

        <div className="erp-system-grid">
          {loading ? (
            <p>Loading connected systems…</p>
          ) : systems.length === 0 ? (
            <p>No CPSE systems yet. Upload materials first.</p>
          ) : (
            systems.map((system) => (
              <div className="erp-system-card" key={system.name}>
                <div className="erp-system-top">
                  <div className="erp-system-logo">{system.name.charAt(0)}</div>
                  <span className="erp-status erp-status-ready">
                    <span className="erp-status-dot" />
                    Adapter Ready
                  </span>
                </div>
                <div className="erp-system-name">{system.name}</div>
                <div className="erp-system-type">Integration adapter</div>
                <div className="erp-system-stats">
                  <div>
                    <span>Material records</span>
                    <strong>{formatNumber(system.materials)}</strong>
                  </div>
                  <div>
                    <span>Match involvements</span>
                    <strong>{formatNumber(system.pending)}</strong>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">DATA EXCHANGE</div>
            <h2>Synchronization</h2>
          </div>
          <button className="erp-primary-button" onClick={handleSync} disabled={syncing}>
            {syncing ? 'Synchronizing…' : 'Sync Material Masters'}
          </button>
        </div>

        <div className="erp-sync-panel">
          <div className="erp-sync-status">
            <div className="erp-sync-indicator">
              <span />
            </div>
            <div>
              <strong>
                {syncing ? 'Synchronization in progress' : 'Ready for synchronization'}
              </strong>
              <p>{lastAction || 'No synchronization is currently running.'}</p>
            </div>
          </div>
          <div className="erp-sync-metrics">
            <div>
              <span>Records pending review</span>
              <strong>{loading ? '—' : formatNumber(pendingReview)}</strong>
            </div>
            <div>
              <span>Approved mappings</span>
              <strong>{loading ? '—' : formatNumber(exportRows.length)}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">APPROVED OUTPUT</div>
            <h2>Mapping Export</h2>
          </div>
          <button className="erp-secondary-button" onClick={handleExport}>
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
              {exportRows.length === 0 ? (
                <tr>
                  <td colSpan={4}>No approved mappings ready for export yet.</td>
                </tr>
              ) : (
                exportRows.map((row) => (
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
                      <span className="erp-approved">Approved</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          <div className="erp-export-footer">
            <span>{exportRows.length} records ready</span>
          </div>
        </div>
      </section>
    </div>
  )
}
