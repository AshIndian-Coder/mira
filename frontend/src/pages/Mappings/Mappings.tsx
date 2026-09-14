import { useCallback, useEffect, useMemo, useState } from 'react'

import { api, formatTimestamp, type Mapping } from '../../lib/api'

type FlatRow = {
  cpse: string
  materialCode: string
  originalDescription: string
  nmc: string
  category: string
  status: string
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase()
  const label =
    normalized === 'PROVISIONAL'
      ? 'Provisional'
      : normalized === 'APPROVED'
        ? 'Approved'
        : status

  const className =
    normalized === 'APPROVED'
      ? 'approved'
      : normalized === 'PROVISIONAL'
        ? 'provisional'
        : 'review'

  return (
    <span className={`mapping-status mapping-status-${className}`}>
      {label}
    </span>
  )
}

export default function Mappings() {
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadMappings = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.listMappings()
      setMappings(response.mappings)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load mappings')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadMappings()
  }, [loadMappings])

  const flatRows: FlatRow[] = useMemo(() => {
    const rows: FlatRow[] = []
    for (const mapping of mappings) {
      for (const entry of mapping.cpse_mappings) {
        rows.push({
          cpse: entry.cpse,
          materialCode: entry.material_code,
          originalDescription: entry.description,
          nmc: mapping.nmc,
          category: entry.category ?? 'General',
          status: mapping.status,
        })
      }
    }
    return rows
  }, [mappings])

  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return flatRows
    return flatRows.filter(
      (row) =>
        row.cpse.toLowerCase().includes(query) ||
        row.materialCode.toLowerCase().includes(query) ||
        row.nmc.toLowerCase().includes(query) ||
        row.originalDescription.toLowerCase().includes(query),
    )
  }, [flatRows, search])

  const commonCodes = new Set(flatRows.map((row) => row.nmc)).size

  const handleGenerate = async () => {
    try {
      setGenerating(true)
      setError(null)
      const result = await api.generateMappings()
      setMessage(
        result.mappings_created > 0
          ? `Created ${result.mappings_created} new mapping cluster(s)`
          : result.message ?? 'No new mappings created',
      )
      await loadMappings()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate mappings')
    } finally {
      setGenerating(false)
    }
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
      link.download = 'mira-mappings-export.json'
      link.click()
      URL.revokeObjectURL(url)
      setMessage(`Exported ${result.total_rows} mapping rows`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  return (
    <div className="page">
      <div className="page-header mapping-page-header">
        <div>
          <div className="eyebrow">CPSE → COMMON MASTER</div>
          <h1>Mappings</h1>
          <p>Track mappings between CPSE material codes and common national material records.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            className="mapping-export-all-button"
            type="button"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? 'Generating…' : 'Generate Mappings'}
          </button>
          <button className="mapping-secondary-button" type="button" onClick={handleExport}>
            Export Mappings
          </button>
        </div>
      </div>

      {message && (
        <div className="common-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="common-info-icon">✓</div>
          <div>
            <strong>Update</strong>
            <p>{message}</p>
          </div>
        </div>
      )}

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Error</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <div className="mapping-summary">
        <div>
          <span>Total Mappings</span>
          <strong>{flatRows.length}</strong>
        </div>
        <div>
          <span>Common Codes</span>
          <strong>{commonCodes}</strong>
        </div>
        <div>
          <span>Clusters</span>
          <strong>{mappings.length}</strong>
        </div>
        <div>
          <span>Latest</span>
          <strong>
            {mappings[0]?.created_at ? formatTimestamp(mappings[0].created_at) : '—'}
          </strong>
        </div>
      </div>

      <div className="mapping-card">
        <div className="mapping-toolbar">
          <input
            className="mapping-search"
            type="text"
            placeholder="Search CPSE, material code, description or NMC…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <div className="mapping-table-wrapper">
          <table className="mapping-table">
            <thead>
              <tr>
                <th>CPSE</th>
                <th>Original Material Code</th>
                <th>Original Description</th>
                <th>Common National Code</th>
                <th>Category</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="mapping-empty">
                    Loading mappings…
                  </td>
                </tr>
              ) : filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="mapping-empty">
                    No mappings yet. Approve matches in Match Review, then click Generate Mappings.
                  </td>
                </tr>
              ) : (
                filteredRows.map((row) => (
                  <tr key={`${row.cpse}-${row.materialCode}-${row.nmc}`}>
                    <td>
                      <strong className="mapping-cpse">{row.cpse}</strong>
                    </td>
                    <td>
                      <span className="mapping-code">{row.materialCode}</span>
                    </td>
                    <td className="mapping-description">{row.originalDescription}</td>
                    <td>
                      <span className="mapping-nmc">{row.nmc}</span>
                    </td>
                    <td>{row.category}</td>
                    <td>
                      <StatusBadge status={row.status} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="mapping-footer">
          Showing {filteredRows.length} of {flatRows.length} mapping rows
        </div>
      </div>
    </div>
  )
}
