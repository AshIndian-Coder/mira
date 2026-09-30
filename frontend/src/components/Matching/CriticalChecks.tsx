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

  if (typeof value === 'object' && value !== null) {
    const obj = value as Record<string, any>
    if ('value' in obj && 'unit' in obj) {
      return `${obj.value} ${obj.unit}`
    }
    if ('diameter' in obj && 'length' in obj) {
      const dia = typeof obj.diameter === 'object' && obj.diameter !== null ? obj.diameter.value : obj.diameter
      const len = typeof obj.length === 'object' && obj.length !== null ? obj.length.value : obj.length
      const unit = (typeof obj.length === 'object' && obj.length?.unit) || (typeof obj.diameter === 'object' && obj.diameter?.unit) || 'MM'
      if ('pitch' in obj) {
        const pitch = typeof obj.pitch === 'object' && obj.pitch !== null ? obj.pitch.value : obj.pitch
        return `M${dia} × ${pitch} × ${len} ${unit}`
      }
      return `M${dia} × ${len} ${unit}`
    }
    if ('nominal_diameter' in obj && 'pitch' in obj) {
      return `M${obj.nominal_diameter} × ${obj.pitch} ${obj.unit || 'MM'}`
    }
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
