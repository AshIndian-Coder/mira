import type { CriticalCheck } from '../../lib/api'

type CriticalChecksProps = {
  checks: CriticalCheck[]
}

function statusIcon(status: CriticalCheck['status']) {
  if (status === 'PASS') return '✓'
  if (status === 'CONFLICT') return '×'
  return '?'
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return 'Not available'
  }

  if (
    typeof value === 'object' &&
    value !== null &&
    'value' in value &&
    'unit' in value
  ) {
    const normalizedValue = value as {
      value: unknown
      unit: unknown
    }

    return `${normalizedValue.value} ${normalizedValue.unit}`
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

function CriticalChecks({ checks }: CriticalChecksProps) {
  if (checks.length === 0) {
    return (
      <div className="critical-checks">
        <h3>Critical Checks</h3>
        <div className="check-row">
          <span>—</span>
          <span>No category-specific checks</span>
          <strong>N/A</strong>
        </div>
      </div>
    )
  }

  return (
    <div className="critical-checks">
      <h3>Critical Checks</h3>

      {checks.map((check) => (
        <div className="check-item" key={check.field}>
          <div className="check-row">
            <span className={`check-icon check-${check.status.toLowerCase()}`}>
              {statusIcon(check.status)}
            </span>

            <span className="check-field">
              {check.field.replace(/_/g, ' ')}
            </span>

            <strong>{check.status}</strong>
          </div>

          {(check.source_value !== null &&
            check.source_value !== undefined) ||
          (check.target_value !== null &&
            check.target_value !== undefined) ? (
            <div className="check-values">
              <div>
                <span>Source</span>
                <strong>{formatValue(check.source_value)}</strong>
              </div>
              <div>
                <span>Target</span>
                <strong>{formatValue(check.target_value)}</strong>
              </div>
            </div>
          ) : null}

          {check.reason && (
            <p className="check-reason">{check.reason}</p>
          )}
        </div>
      ))}
    </div>
  )
}

export default CriticalChecks
