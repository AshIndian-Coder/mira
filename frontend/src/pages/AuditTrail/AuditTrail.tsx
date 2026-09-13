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
    <main className="page-content audit-page">
      <div className="page-header audit-header">
        <div>
          <div className="eyebrow">GOVERNANCE & TRACEABILITY</div>
          <h1>Audit Trail</h1>
          <p>Track material decisions, mapping changes and governance actions.</p>
        </div>
        <div className="audit-header-status">
          <span className="status-dot" />
          Audit trail connected
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

      <section className="audit-summary">
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

        <div className="audit-table">
          <div className="audit-table-head">
            <span>Action</span>
            <span>Entity</span>
            <span>Activity</span>
            <span>Actor</span>
            <span>Timestamp</span>
            <span>Reference</span>
          </div>

          {loading ? (
            <div className="audit-empty">
              <strong>Loading audit events…</strong>
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="audit-empty">
              <strong>No audit events found</strong>
              <span>Approve or reject matches to populate the audit trail.</span>
            </div>
          ) : (
            filteredEntries.map((entry) => (
              <div className="audit-table-row" key={`${entry.reference}-${entry.timestamp}`}>
                <div>
                  <span className={`audit-action ${actionClass(entry.action)}`}>
                    <span className="audit-action-icon">{actionIcon(entry.action)}</span>
                    {entry.action}
                  </span>
                </div>
                <div className="audit-entity">
                  <strong>{entry.entity}</strong>
                  <small>{entry.entityType}</small>
                </div>
                <div className="audit-description">{entry.description}</div>
                <div className="audit-actor">
                  <strong>{entry.actor}</strong>
                </div>
                <div className="audit-time">{entry.timestamp}</div>
                <div className="audit-reference">
                  <span>{entry.reference}</span>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="audit-footer">
          <span>
            Showing {filteredEntries.length} of {formatNumber(totalEvents)} events
          </span>
        </div>
      </section>
    </main>
  )
}
