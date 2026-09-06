import { useMemo, useState } from 'react'

type AuditAction =
  | 'Approved'
  | 'Rejected'
  | 'Sent for Review'
  | 'Created'
  | 'Mapped'
  | 'Exported'

type AuditEntry = {
  id: number
  action: AuditAction
  entity: string
  entityType: string
  description: string
  actor: string
  role: string
  timestamp: string
  status: 'Success' | 'Pending'
  reference: string
}

const auditEntries: AuditEntry[] = [
  {
    id: 1,
    action: 'Approved',
    entity: 'VAL-00921',
    entityType: 'Material Mapping',
    description: 'Approved mapping to MIRA-VAL-000001',
    actor: 'Data Steward',
    role: 'Data Steward',
    timestamp: '06 Sep 2026, 19:42',
    status: 'Success',
    reference: 'MAP-000127',
  },
  {
    id: 2,
    action: 'Mapped',
    entity: '10003741',
    entityType: 'Material Mapping',
    description: 'Mapped IOCL material to common material',
    actor: 'Data Steward',
    role: 'Data Steward',
    timestamp: '06 Sep 2026, 19:38',
    status: 'Success',
    reference: 'MAP-000126',
  },
  {
    id: 3,
    action: 'Sent for Review',
    entity: 'BV-004821',
    entityType: 'Match Candidate',
    description: 'Critical specification ambiguity requires review',
    actor: 'MIRA Matching Engine',
    role: 'System',
    timestamp: '06 Sep 2026, 19:31',
    status: 'Pending',
    reference: 'MAT-000843',
  },
  {
    id: 4,
    action: 'Approved',
    entity: 'NT-VAL-1842',
    entityType: 'Common Material',
    description: 'Approved common material MIRA-VAL-000002',
    actor: 'Data Steward',
    role: 'Data Steward',
    timestamp: '06 Sep 2026, 18:54',
    status: 'Success',
    reference: 'CM-000042',
  },
  {
    id: 5,
    action: 'Created',
    entity: 'MIRA-ELC-000001',
    entityType: 'Common Material',
    description: 'Common material record created from approved match',
    actor: 'MIRA Harmonization',
    role: 'System',
    timestamp: '06 Sep 2026, 18:41',
    status: 'Success',
    reference: 'CM-000041',
  },
  {
    id: 6,
    action: 'Rejected',
    entity: 'SAIL-FST-0082',
    entityType: 'Match Candidate',
    description: 'Rejected candidate due to incompatible specifications',
    actor: 'Data Steward',
    role: 'Data Steward',
    timestamp: '06 Sep 2026, 17:26',
    status: 'Success',
    reference: 'MAT-000817',
  },
  {
    id: 7,
    action: 'Exported',
    entity: 'Mapping Batch #07',
    entityType: 'ERP Export',
    description: 'Approved CPSE-to-common mappings prepared for export',
    actor: 'Data Steward',
    role: 'Data Steward',
    timestamp: '06 Sep 2026, 16:12',
    status: 'Success',
    reference: 'EXP-000007',
  },
  {
    id: 8,
    action: 'Sent for Review',
    entity: 'POWER CONNECTOR 415V 32A',
    entityType: 'Match Candidate',
    description: 'Voltage specification requires human validation',
    actor: 'MIRA Matching Engine',
    role: 'System',
    timestamp: '06 Sep 2026, 15:48',
    status: 'Pending',
    reference: 'MAT-000791',
  },
]

const actionOptions = [
  'All Actions',
  'Approved',
  'Rejected',
  'Sent for Review',
  'Created',
  'Mapped',
  'Exported',
]

const entityOptions = [
  'All Entities',
  'Material Mapping',
  'Match Candidate',
  'Common Material',
  'ERP Export',
]

function actionClass(action: AuditAction) {
  switch (action) {
    case 'Approved':
    case 'Mapped':
    case 'Exported':
      return 'audit-action-success'
    case 'Rejected':
      return 'audit-action-danger'
    case 'Sent for Review':
      return 'audit-action-review'
    default:
      return 'audit-action-neutral'
  }
}

function actionIcon(action: AuditAction) {
  switch (action) {
    case 'Approved':
      return '✓'
    case 'Rejected':
      return '×'
    case 'Sent for Review':
      return '!'
    case 'Created':
      return '+'
    case 'Mapped':
      return '↔'
    case 'Exported':
      return '↑'
  }
}

export default function AuditTrail() {
  const [search, setSearch] = useState('')
  const [actionFilter, setActionFilter] = useState('All Actions')
  const [entityFilter, setEntityFilter] = useState('All Entities')

  const filteredEntries = useMemo(() => {
    const query = search.trim().toLowerCase()

    return auditEntries.filter((entry) => {
      const matchesSearch =
        !query ||
        entry.entity.toLowerCase().includes(query) ||
        entry.description.toLowerCase().includes(query) ||
        entry.actor.toLowerCase().includes(query) ||
        entry.reference.toLowerCase().includes(query)

      const matchesAction =
        actionFilter === 'All Actions' || entry.action === actionFilter

      const matchesEntity =
        entityFilter === 'All Entities' || entry.entityType === entityFilter

      return matchesSearch && matchesAction && matchesEntity
    })
  }, [search, actionFilter, entityFilter])

  return (
    <main className="page-content audit-page">
      <div className="page-header audit-header">
        <div>
          <div className="eyebrow">GOVERNANCE & TRACEABILITY</div>
          <h1>Audit Trail</h1>
          <p>
            Track material decisions, mapping changes and governance actions
            across the national material master.
          </p>
        </div>

        <div className="audit-header-status">
          <span className="status-dot" />
          Audit logging active
        </div>
      </div>

      <section className="audit-summary">
        <div className="audit-summary-card">
          <span>Total Events</span>
          <strong>12,847</strong>
          <small>Recorded actions</small>
        </div>

        <div className="audit-summary-card">
          <span>Approvals</span>
          <strong>6,184</strong>
          <small>Governance decisions</small>
        </div>

        <div className="audit-summary-card">
          <span>Pending Actions</span>
          <strong>326</strong>
          <small>Require steward attention</small>
        </div>

        <div className="audit-summary-card">
          <span>Active Users</span>
          <strong>14</strong>
          <small>Contributors this month</small>
        </div>
      </section>

      <section className="audit-card">
        <div className="audit-card-header">
          <div>
            <h2>Activity Log</h2>
            <p>
              Every material governance action is recorded with its source,
              actor and timestamp.
            </p>
          </div>

          <button className="audit-export-button" type="button">
            Export Audit Log
          </button>
        </div>

        <div className="audit-filters">
          <div className="audit-search">
            <span>⌕</span>
            <input
              type="text"
              placeholder="Search material, reference, actor..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <select
            value={actionFilter}
            onChange={(event) => setActionFilter(event.target.value)}
          >
            {actionOptions.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>

          <select
            value={entityFilter}
            onChange={(event) => setEntityFilter(event.target.value)}
          >
            {entityOptions.map((option) => (
              <option key={option}>{option}</option>
            ))}
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

          {filteredEntries.map((entry) => (
            <div className="audit-table-row" key={entry.id}>
              <div>
                <span className={`audit-action ${actionClass(entry.action)}`}>
                  <span className="audit-action-icon">
                    {actionIcon(entry.action)}
                  </span>
                  {entry.action}
                </span>
              </div>

              <div className="audit-entity">
                <strong>{entry.entity}</strong>
                <small>{entry.entityType}</small>
              </div>

              <div className="audit-description">
                {entry.description}
              </div>

              <div className="audit-actor">
                <strong>{entry.actor}</strong>
                <small>{entry.role}</small>
              </div>

              <div className="audit-time">{entry.timestamp}</div>

              <div className="audit-reference">
                <span>{entry.reference}</span>
                {entry.status === 'Pending' && (
                  <small>Pending</small>
                )}
              </div>
            </div>
          ))}

          {filteredEntries.length === 0 && (
            <div className="audit-empty">
              <strong>No audit events found</strong>
              <span>Try changing the search or filters.</span>
            </div>
          )}
        </div>

        <div className="audit-footer">
          <span>
            Showing {filteredEntries.length} of {auditEntries.length} recent
            demo events
          </span>
          <span>All timestamps shown in system time</span>
        </div>
      </section>

      <section className="audit-governance">
        <div>
          <div className="audit-governance-icon">✓</div>
          <div>
            <h3>Traceable governance</h3>
            <p>
              MIRA preserves the original CPSE material identity while
              recording every approval, rejection, mapping and export action.
            </p>
          </div>
        </div>

        <div className="audit-governance-meta">
          <span>Retention policy</span>
          <strong>System managed</strong>
        </div>
      </section>
    </main>
  )
}
