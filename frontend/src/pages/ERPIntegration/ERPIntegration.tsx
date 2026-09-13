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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const [cpseRes, overview, exportRes, mappingsRes] = await Promise.all([
          api.analyticsByCpse(),
          api.analyticsOverview(),
          api.exportMappingsFlat(),
          api.listMappings(),
        ])

        setSystems(
          cpseRes.cpse_breakdown.map((row) => ({
            name: row.cpse,
            materials: row.material_count,
            pending: row.candidate_pair_involvements,
          })),
        )
        setPendingReview(overview.review_pending)
        const mappingStatusByNmc = new Map(
          mappingsRes.mappings.map((mapping) => [mapping.nmc, mapping.status]),
        )

        setExportRows(
          exportRes.rows.map((row) => ({
            cpse: row.cpse,
            code: row.cpse_material_code,
            nmc: row.nmc,
            status: mappingStatusByNmc.get(row.nmc) ?? 'UNKNOWN',
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
          <p>Review CPSE material sources and prepare harmonization mappings for ERP exchange.</p>
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
            <h2>Ingested Source Systems</h2>
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
                    Source Available
                  </span>
                </div>
                <div className="erp-system-name">{system.name}</div>
                <div className="erp-system-type">CPSE material source</div>
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
            <div className="eyebrow">INTEGRATION STATUS</div>
            <h2>ERP Exchange</h2>
          </div>
          <span className="erp-status erp-status-ready">
            <span className="erp-status-dot" />
            Integration Ready
          </span>
        </div>

        <div className="erp-sync-panel">
          <div className="erp-sync-status">
            <div className="erp-sync-indicator">
              <span />
            </div>
            <div>
              <strong>Ready for ERP data exchange</strong>
              <p>
                MIRA currently supports material ingestion and mapping export.
                Live ERP/SAP synchronization is not configured in this prototype.
              </p>
            </div>
          </div>

          <div className="erp-sync-metrics">
            <div>
              <span>Records pending review</span>
              <strong>{loading ? '—' : formatNumber(pendingReview)}</strong>
            </div>
            <div>
              <span>Mapping records available</span>
              <strong>{loading ? '—' : formatNumber(exportRows.length)}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="erp-section">
        <div className="erp-section-header">
          <div>
            <div className="eyebrow">MAPPING OUTPUT</div>
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
                  <td colSpan={4}>No mapping records ready for export yet.</td>
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
                      <span
                        className={
                          row.status === 'APPROVED'
                            ? 'erp-approved'
                            : 'erp-mapping-status'
                        }
                      >
                        {row.status.replace(/_/g, ' ')}
                      </span>
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
