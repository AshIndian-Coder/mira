import type { CriticalCheck } from '../../lib/api'

type CriticalChecksProps = {
  checks: CriticalCheck[]
}

function statusIcon(status: CriticalCheck['status']) {
  if (status === 'PASS') return '✓'
  if (status === 'CONFLICT') return '×'
  return '?'
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
        <div className="check-row" key={check.field}>
          <span>{statusIcon(check.status)}</span>
          <span>{check.field.replace(/_/g, ' ')}</span>
          <strong>{check.status}</strong>
        </div>
      ))}
    </div>
  )
}

export default CriticalChecks
