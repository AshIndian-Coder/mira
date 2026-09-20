import Badge from '../UI/Badge'
import type { Candidate } from '../../lib/api'
import { formatPercent } from '../../lib/api'

type FieldDifferenceTableProps = {
  candidate: Candidate
}

type FieldComparisonRow = {
  key: string
  label: string
  sourceValue: string
  targetValue: string
  status: 'SAME' | 'CONFLICT' | 'MISSING' | 'UNKNOWN' | 'SIMILAR' | 'DIFFERENT'
  statusLabel: string
  badgeVariant: 'success' | 'danger' | 'warning' | 'neutral' | 'info' | 'review'
  reason?: string
  isCritical?: boolean
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  if (
    typeof value === 'object' &&
    value !== null &&
    'value' in value &&
    'unit' in value
  ) {
    const valObj = value as { value: unknown; unit: unknown }
    return `${valObj.value} ${valObj.unit}`
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

function formatFieldLabel(field: string): string {
  const customLabels: Record<string, string> = {
    category: 'Category',
    material_grade: 'Material Grade',
    dimensions: 'Dimensions / Size',
    pressure_rating: 'Pressure Rating',
    voltage_class: 'Voltage Class',
    nominal_bore: 'Nominal Bore',
    metric_thread: 'Metric Thread',
    description: 'Description Text',
  }
  return (
    customLabels[field] ||
    field
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase())
  )
}

function normalizeSimple(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, ' ')
}

export function buildFieldComparisonRows(candidate: Candidate): FieldComparisonRow[] {
  const rows: FieldComparisonRow[] = []
  const processedFields = new Set<string>()

  // 1. Description Row
  const descSource = candidate.source_description
  const descTarget = candidate.target_description
  const isExactDesc = normalizeSimple(descSource) === normalizeSimple(descTarget)
  const semanticScore = candidate.scores?.semantic_similarity ?? 0
  const textScore = candidate.scores?.text_similarity ?? 0

  let descStatus: FieldComparisonRow['status'] = 'DIFFERENT'
  let descBadgeVariant: FieldComparisonRow['badgeVariant'] = 'neutral'
  let descStatusLabel = 'DIFFERENT'
  let descReason = `Description semantic similarity: ${formatPercent(semanticScore, 0)} · Token similarity: ${formatPercent(textScore, 0)}`

  if (isExactDesc) {
    descStatus = 'SAME'
    descBadgeVariant = 'success'
    descStatusLabel = 'SAME'
    descReason = 'Exact description text match'
  } else if (semanticScore > 0) {
    descStatus = 'SIMILAR'
    descBadgeVariant = 'info'
    descStatusLabel = `${formatPercent(semanticScore, 0)} Similar`
    descReason = `Semantic similarity: ${formatPercent(semanticScore, 0)} · Token similarity: ${formatPercent(textScore, 0)}`
  }

  rows.push({
    key: 'description',
    label: 'Description Text',
    sourceValue: descSource,
    targetValue: descTarget,
    status: descStatus,
    statusLabel: descStatusLabel,
    badgeVariant: descBadgeVariant,
    reason: descReason,
    isCritical: false,
  })
  processedFields.add('description')

  // 2. Critical Checks Rows (Material Grade, Dimensions, Pressure Rating, Voltage Class, etc.)
  if (candidate.critical_checks && candidate.critical_checks.length > 0) {
    for (const check of candidate.critical_checks) {
      processedFields.add(check.field)
      const srcVal = formatValue(check.source_value)
      const tgtVal = formatValue(check.target_value)

      let rowStatus: FieldComparisonRow['status'] = 'UNKNOWN'
      let rowBadge: FieldComparisonRow['badgeVariant'] = 'neutral'
      let rowLabel = 'UNKNOWN'

      if (check.status === 'PASS') {
        rowStatus = 'SAME'
        rowBadge = 'success'
        rowLabel = 'SAME'
      } else if (check.status === 'CONFLICT') {
        rowStatus = 'CONFLICT'
        rowBadge = 'danger'
        rowLabel = 'CONFLICT'
      } else if (check.status === 'UNKNOWN') {
        const srcMissing = check.source_value === null || check.source_value === undefined || check.source_value === ''
        const tgtMissing = check.target_value === null || check.target_value === undefined || check.target_value === ''

        if (srcMissing && tgtMissing) {
          rowStatus = 'UNKNOWN'
          rowBadge = 'neutral'
          rowLabel = 'UNKNOWN'
        } else if (srcMissing) {
          rowStatus = 'MISSING'
          rowBadge = 'warning'
          rowLabel = 'MISSING (Source)'
        } else {
          rowStatus = 'MISSING'
          rowBadge = 'warning'
          rowLabel = 'MISSING (Target)'
        }
      } else if (check.status === 'FAIL' || check.status === 'DIFFERENT') {
        rowStatus = 'DIFFERENT'
        rowBadge = 'neutral'
        rowLabel = 'DIFFERENT'
      }

      rows.push({
        key: check.field,
        label: formatFieldLabel(check.field),
        sourceValue: srcVal,
        targetValue: tgtVal,
        status: rowStatus,
        statusLabel: rowLabel,
        badgeVariant: rowBadge,
        reason: check.reason,
        isCritical: true,
      })
    }
  }

  return rows
}

function FieldDifferenceTable({ candidate }: FieldDifferenceTableProps) {
  const rows = buildFieldComparisonRows(candidate)
  const conflicts = rows.filter((r) => r.status === 'CONFLICT')
  const missing = rows.filter((r) => r.status === 'MISSING')

  return (
    <div className="field-difference-section" style={{ marginBottom: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
            Why This Needs Review (Field-Level Differences)
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: '11.5px', color: 'var(--text-muted)' }}>
            Direct comparison of extracted specifications and critical safety gates.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          {conflicts.length > 0 && (
            <Badge variant="danger">
              {conflicts.length} {conflicts.length === 1 ? 'Conflict' : 'Conflicts'}
            </Badge>
          )}
          {missing.length > 0 && (
            <Badge variant="warning">
              {missing.length} Missing
            </Badge>
          )}
          {conflicts.length === 0 && missing.length === 0 && (
            <Badge variant="success">All Specs Aligned</Badge>
          )}
        </div>
      </div>

      {conflicts.length > 0 && (
        <div
          style={{
            padding: '10px 14px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--danger-bg)',
            border: '1px solid var(--danger-border)',
            color: 'var(--danger-text)',
            fontSize: '12px',
            marginBottom: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <strong style={{ fontWeight: 800 }}>⚠️ Critical Conflict:</strong>
          <span>
            {conflicts.map((c) => `${c.label} (${c.sourceValue} vs ${c.targetValue})`).join('; ')}.
            Automatic acceptance is blocked to ensure procurement safety.
          </span>
        </div>
      )}

      <div
        style={{
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          background: 'var(--bg-surface)',
        }}
      >
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '12px',
            textAlign: 'left',
          }}
        >
          <thead>
            <tr
              style={{
                background: 'var(--bg-surface-subtle)',
                borderBottom: '1px solid var(--border-default)',
                color: 'var(--text-muted)',
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              <th style={{ padding: '10px 14px', width: '22%' }}>Specification Field</th>
              <th style={{ padding: '10px 14px', width: '32%' }}>
                Source ({candidate.source_cpse})
              </th>
              <th style={{ padding: '10px 14px', width: '32%' }}>
                Target ({candidate.target_cpse})
              </th>
              <th style={{ padding: '10px 14px', width: '14%', textAlign: 'right' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const isConflictRow = row.status === 'CONFLICT'
              const rowBg = isConflictRow
                ? 'rgba(239, 68, 68, 0.04)'
                : idx % 2 === 1
                  ? 'var(--bg-surface-subtle)'
                  : 'var(--bg-surface)'

              return (
                <tr
                  key={row.key}
                  style={{
                    background: rowBg,
                    borderBottom:
                      idx < rows.length - 1
                        ? '1px solid var(--border-subtle)'
                        : 'none',
                    transition: 'background 120ms ease',
                  }}
                >
                  <td style={{ padding: '10px 14px', fontWeight: 650, color: 'var(--text-primary)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {row.label}
                      {row.isCritical && (
                        <span
                          title="Category-specific critical safety field"
                          style={{
                            fontSize: '9.5px',
                            padding: '1px 5px',
                            borderRadius: '3px',
                            background: '#e0e7ff',
                            color: '#3730a3',
                            fontWeight: 700,
                          }}
                        >
                          CRITICAL
                        </span>
                      )}
                    </div>
                  </td>
                  <td
                    style={{
                      padding: '10px 14px',
                      color: row.sourceValue === '—' ? 'var(--text-dim)' : 'var(--text-secondary)',
                      fontFamily: row.key === 'description' ? 'inherit' : 'var(--font-mono)',
                      fontSize: row.key === 'description' ? '12px' : '11.5px',
                    }}
                  >
                    {row.sourceValue}
                  </td>
                  <td
                    style={{
                      padding: '10px 14px',
                      color: row.targetValue === '—' ? 'var(--text-dim)' : 'var(--text-secondary)',
                      fontFamily: row.key === 'description' ? 'inherit' : 'var(--font-mono)',
                      fontSize: row.key === 'description' ? '12px' : '11.5px',
                    }}
                  >
                    {row.targetValue}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <Badge variant={row.badgeVariant}>{row.statusLabel}</Badge>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default FieldDifferenceTable
