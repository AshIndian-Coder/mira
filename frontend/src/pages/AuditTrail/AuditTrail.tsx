import { useCallback, useEffect, useMemo, useState } from 'react'

import { api, formatNumber, formatTimestamp, type AuditEvent } from '../../lib/api'

type AuditEntry = {
  id: number
  action: string
  entity: string
  entityType: string
  description: string
  actor: string
  timestamp: string
  reference: string
}

function mapAuditEvent(event: AuditEvent, index: number): AuditEntry {
  const action =
    event.event_type === 'MATCH_APPROVED'
      ? 'Approved'
      : event.event_type === 'MATCH_REJECTED'
        ? 'Rejected'
        : event.event_type.replace(/_/g, ' ')

  return {
    id: event.candidate_id ?? index,
    action,
    entity: event.source_code ?? '—',
    entityType: 'Material Mapping',
    description: `${event.source_cpse ?? ''} ${event.source_code ?? ''} ↔ ${event.target_cpse ?? ''} ${event.target_code ?? ''}`.trim(),
    actor: event.actor ?? 'System',
    timestamp: formatTimestamp(event.timestamp),
    reference: event.candidate_id ? `CND-${event.candidate_id}` : '—',
  }
}

function actionClass(action: string) {
  if (action === 'Approved') return 'audit-action-success'
  if (action === 'Rejected') return 'audit-action-danger'
  if (action.includes('Review')) return 'audit-action-review'
  return 'audit-action-neutral'
}

function actionIcon(action: string) {
  if (action === 'Approved') return '✓'
  if (action === 'Rejected') return '×'
  if (action.includes('Review')) return '!'
  return '•'
}

export default function AuditTrail() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [totalEvents, setTotalEvents] = useState(0)
  const [search, setSearch] = useState('')
  const [actionFilter, setActionFilter] = useState('All Actions')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadAudit = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.listAudit(0, 200)
      setTotalEvents(response.total)
      setEntries(response.events.map(mapAuditEvent))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit log')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAudit()
  }, [loadAudit])

  const filteredEntries = useMemo(() => {
    const query = search.trim().toLowerCase()
    return entries.filter((entry) => {
      const matchesSearch =
        !query ||
        entry.entity.toLowerCase().includes(query) ||
        entry.description.toLowerCase().includes(query) ||
        entry.actor.toLowerCase().includes(query) ||
        entry.reference.toLowerCase().includes(query)

      const matchesAction =
        actionFilter === 'All Actions' || entry.action === actionFilter

      return matchesSearch && matchesAction
    })
  }, [entries, search, actionFilter])

  const approvals = entries.filter((entry) => entry.action === 'Approved').length

  const handleExport = async () => {
    try {
      const response = await api.exportAudit()
      const blob = new Blob([JSON.stringify(response.events, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'mira-audit-export.json'
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  return (
    <div className="page audit-page">
      <div className="page-header audit-header">
        <div>
          <div className="eyebrow">GOVERNANCE & TRACEABILITY</div>
          <h1>Audit Trail</h1>
          <p>Track material decisions, mapping changes and governance actions.</p>
        </div>
        <div className="dashboard-status">
          <span className="dashboard-status-dot" />
          <span>Audit trail connected</span>
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

      <section className="audit-summary" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="audit-summary-card">
          <span>Total Events</span>
          <strong>{loading ? '—' : formatNumber(totalEvents)}</strong>
          <small>Recorded actions</small>
        </div>
        <div className="audit-summary-card">
          <span>Approvals</span>
          <strong>{loading ? '—' : formatNumber(approvals)}</strong>
          <small>Governance decisions</small>
        </div>
        <div className="audit-summary-card">
          <span>Filtered View</span>
          <strong>{loading ? '—' : formatNumber(filteredEntries.length)}</strong>
          <small>Matching current filters</small>
        </div>
      </section>

      <section className="audit-card">
        <div className="audit-card-header">
          <div>
            <h2>Activity Log</h2>
            <p>Every material governance action is recorded with its source, actor and timestamp.</p>
          </div>
          <button className="audit-export-button" type="button" onClick={handleExport}>
            Export Audit Log
          </button>
        </div>

        <div className="audit-filters">
          <div className="audit-search">
            <span>⌕</span>
            <input
              type="text"
              placeholder="Search material, reference, actor…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <select value={actionFilter} onChange={(event) => setActionFilter(event.target.value)}>
            <option>All Actions</option>
            <option>Approved</option>
            <option>Rejected</option>
          </select>
        </div>

        <div className="mapping-table-wrapper">
          <table className="mapping-table">
            <thead>
              <tr>
                <th style={{ width: '130px' }}>Action</th>
                <th style={{ width: '220px' }}>Entity</th>
                <th>Activity Description</th>
                <th style={{ width: '140px' }}>Actor</th>
                <th style={{ width: '190px' }}>Timestamp</th>
                <th style={{ width: '110px' }}>Reference</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="mapping-empty">
                    Loading audit events…
                  </td>
                </tr>
              ) : filteredEntries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="mapping-empty">
                    No audit events found. Approve or reject matches to populate the audit trail.
                  </td>
                </tr>
              ) : (
                filteredEntries.map((entry) => (
                  <tr key={`${entry.reference}-${entry.timestamp}`}>
                    <td>
                      <span className={`audit-action ${actionClass(entry.action)}`}>
                        <span className="audit-action-icon">{actionIcon(entry.action)}</span>
                        {entry.action}
                      </span>
                    </td>
                    <td>
                      <div className="audit-entity">
                        <strong
                          className="mapping-code"
                          style={{
                            whiteSpace: 'nowrap',
                            display: 'inline-block',
                            letterSpacing: '0.01em',
                          }}
                        >
                          {entry.entity}
                        </strong>
                        <small style={{ marginTop: '3px' }}>{entry.entityType}</small>
                      </div>
                    </td>
                    <td className="mapping-description">{entry.description}</td>
                    <td>
                      <strong style={{ fontSize: '12px', color: '#1e293b' }}>{entry.actor}</strong>
                    </td>
                    <td style={{ fontSize: '12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {entry.timestamp}
                    </td>
                    <td>
                      <span className="mapping-code" style={{ whiteSpace: 'nowrap' }}>
                        {entry.reference}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="audit-footer">
          <span>
            Showing {filteredEntries.length} of {formatNumber(totalEvents)} events
          </span>
        </div>
      </section>
    </div>
  )
}
