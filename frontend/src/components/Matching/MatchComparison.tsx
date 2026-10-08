import Badge from '../UI/Badge'
import Button from '../UI/Button'
import CriticalChecks from './CriticalChecks'
import FieldDifferenceTable from './FieldDifferenceTable'
import ScoreGrid from './ScoreGrid'
import type { Candidate } from '../../lib/api'
import { formatPercent } from '../../lib/api'

type MatchComparisonProps = {
  candidate: Candidate | null
  onApprove?: () => void
  onReject?: () => void
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

  const hasMarginEvidence =
    candidate.explanation != null &&
    candidate.explanation.best_score != null &&
    candidate.explanation.best_score !== undefined

  const hasSecondBest =
    hasMarginEvidence &&
    candidate.explanation?.second_best_score != null &&
    candidate.explanation?.second_best_score !== undefined

  const hasMarginDelta =
    hasMarginEvidence &&
    candidate.explanation?.score_margin != null &&
    candidate.explanation?.score_margin !== undefined

  return (
    <div className="section-card comparison">
      <div className="section-header">
        <div>
          <span className="eyebrow">CANDIDATE COMPARISON</span>
          <h2>Potential Equivalent Materials</h2>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Badge variant={badgeVariant}>{candidate.engine_decision}</Badge>
          <span
            style={{
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              padding: '3px 8px',
              borderRadius: 'var(--radius-sm)',
              background: '#f1f5f9',
              color: '#334155',
            }}
          >
            {formatPercent(candidate.scores.final_score, 0)} Match
          </span>
        </div>
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

      {/* Field-Level Difference Explanation */}
      <FieldDifferenceTable candidate={candidate} />

      {/* Observability: Candidate Separation Margin Evidence */}
      {hasMarginEvidence && (
        <div
          style={{
            marginBottom: '24px',
            padding: '14px 16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-default)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '10px',
            }}
          >
            <h4
              style={{
                margin: 0,
                fontSize: '13px',
                fontWeight: 700,
                color: 'var(--text-primary)',
              }}
            >
              Candidate Separation Evidence
            </h4>
            <span style={{ fontSize: '10.5px', color: 'var(--text-muted)' }}>
              Observational evidence only
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
              gap: '10px',
            }}
          >
            <div
              style={{
                background: 'var(--bg-surface)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <span
                style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  display: 'block',
                  fontWeight: 600,
                }}
              >
                Top Candidate Score
              </span>
              <strong
                style={{
                  fontSize: '14px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                }}
              >
                {candidate.explanation?.best_score != null
                  ? `${(Number(candidate.explanation.best_score) * 100).toFixed(1)}%`
                  : formatPercent(candidate.scores.final_score, 1)}
              </strong>
            </div>

            <div
              style={{
                background: 'var(--bg-surface)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <span
                style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  display: 'block',
                  fontWeight: 600,
                }}
              >
                Runner-Up Candidate Score
              </span>
              <strong
                style={{
                  fontSize: '14px',
                  fontFamily: 'var(--font-mono)',
                  color: hasSecondBest ? 'var(--text-primary)' : 'var(--text-dim)',
                }}
              >
                {hasSecondBest
                  ? `${(Number(candidate.explanation?.second_best_score) * 100).toFixed(1)}%`
                  : '— (Only Candidate)'}
              </strong>
            </div>

            <div
              style={{
                background: 'var(--bg-surface)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <span
                style={{
                  fontSize: '10px',
                  color: 'var(--text-muted)',
                  display: 'block',
                  fontWeight: 600,
                }}
              >
                Separation Margin (Δ)
              </span>
              <strong
                style={{
                  fontSize: '14px',
                  fontFamily: 'var(--font-mono)',
                  color: hasMarginDelta ? 'var(--text-primary)' : 'var(--text-dim)',
                }}
              >
                {hasMarginDelta
                  ? `+${(Number(candidate.explanation?.score_margin) * 100).toFixed(1)}%`
                  : 'N/A (Sole Match)'}
              </strong>
            </div>
          </div>
          <p
            style={{
              margin: '8px 0 0',
              fontSize: '11px',
              color: 'var(--text-muted)',
              lineHeight: 1.4,
            }}
          >
            Margin reflects deterministic ranking separation between top candidates. It is shown for review context and does not alter automated decisions.
          </p>
        </div>
      )}

      <div className="score-section">
        <h3>AI Assessment Breakdown</h3>
        <ScoreGrid scores={candidate.scores} />
      </div>

      <CriticalChecks checks={candidate.critical_checks} />

      <div className="decision">
        <div>
          <span>Final score</span>
          <strong>{formatPercent(candidate.scores.final_score, 0)}</strong>
        </div>

        {onApprove && onReject ? (
          <div className="decision-actions">
            <Button
              onClick={onReject}
              disabled={acting}
              title="Mark these two materials as different. The pair is closed and will not be proposed again."
            >
              Reject
            </Button>
            <Button
              onClick={onApprove}
              variant="primary"
              disabled={acting}
              title="Confirm these are the same item. The decision is final, is logged against your name, and feeds mapping generation."
            >
              {acting ? 'Saving…' : 'Approve Mapping'}
            </Button>
          </div>
        ) : (
          <div className="decision-actions">
            <span className="login-hint">
              Your role can view this queue but cannot approve or reject. Only Material Reviewers
              and Administrators can action a candidate.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default MatchComparison
