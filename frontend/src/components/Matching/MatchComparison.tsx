import Badge from '../UI/Badge'
import Button from '../UI/Button'
import CriticalChecks from './CriticalChecks'
import ScoreGrid from './ScoreGrid'
import type { Candidate } from '../../lib/api'
import { formatPercent } from '../../lib/api'

type MatchComparisonProps = {
  candidate: Candidate | null
  onApprove: () => void
  onReject: () => void
  acting?: boolean
}

function MaterialPanel({
  source,
  code,
  description,
  grade,
}: {
  source: string
  code: string
  description: string
  grade?: string | null
}) {
  return (
    <div className="material-panel">
      <span className="source-label">{source}</span>
      <h3>{code}</h3>
      <p>{description}</p>
      {grade && (
        <div className="attribute">
          <span>Material</span>
          <strong>{grade}</strong>
        </div>
      )}
    </div>
  )
}

function MatchComparison({
  candidate,
  onApprove,
  onReject,
  acting = false,
}: MatchComparisonProps) {
  if (!candidate) {
    return (
      <div className="section-card comparison">
        <div className="section-header">
          <div>
            <span className="eyebrow">CANDIDATE COMPARISON</span>
            <h2>Select a match to review</h2>
          </div>
        </div>
        <p>Choose a candidate from the queue to compare materials.</p>
      </div>
    )
  }

  const badgeVariant =
    candidate.engine_decision === 'HIGH_CONFIDENCE'
      ? 'success'
      : candidate.engine_decision === 'DIFFERENT'
        ? 'neutral'
        : 'review'

  return (
    <div className="section-card comparison">
      <div className="section-header">
        <div>
          <span className="eyebrow">CANDIDATE COMPARISON</span>
          <h2>Potential Equivalent Materials</h2>
        </div>
        <Badge variant={badgeVariant}>{candidate.engine_decision}</Badge>
      </div>

      <div className="material-columns">
        <MaterialPanel
          source={`CPSE · ${candidate.source_cpse}`}
          code={candidate.source_code}
          description={candidate.source_description}
        />
        <MaterialPanel
          source={`CPSE · ${candidate.target_cpse}`}
          code={candidate.target_code}
          description={candidate.target_description}
        />
      </div>

      <div className="score-section">
        <h3>AI Assessment</h3>
        <ScoreGrid scores={candidate.scores} />
      </div>

      <CriticalChecks checks={candidate.critical_checks} />

      <div className="decision">
        <div>
          <span>Final score</span>
          <strong>{formatPercent(candidate.scores.final_score, 0)}</strong>
        </div>

        <div className="decision-actions">
          <Button onClick={onReject} disabled={acting}>
            Reject
          </Button>
          <Button onClick={onApprove} variant="primary" disabled={acting}>
            {acting ? 'Saving…' : 'Approve Mapping'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default MatchComparison
