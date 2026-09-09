import type { Candidate } from '../../lib/api'
import { formatPercent } from '../../lib/api'

type MatchListProps = {
  candidates: Candidate[]
  selectedId: number | null
  onSelect: (candidate: Candidate) => void
  loading?: boolean
}

function MatchList({
  candidates,
  selectedId,
  onSelect,
  loading = false,
}: MatchListProps) {
  return (
    <div className="section-card match-list">
      <div className="section-header">
        <div>
          <h2>Candidate Matches</h2>
          <p>Sorted by review priority.</p>
        </div>
      </div>

      {loading ? (
        <div className="match-item">
          <span>Loading review queue…</span>
        </div>
      ) : candidates.length === 0 ? (
        <div className="match-item">
          <span>No pending reviews. Upload materials and run matching first.</span>
        </div>
      ) : (
        candidates.map((candidate) => (
          <button
            type="button"
            key={candidate.id}
            className={`match-item ${selectedId === candidate.id ? 'selected' : ''}`}
            onClick={() => onSelect(candidate)}
            style={{
              width: '100%',
              border: 'none',
              background: 'transparent',
              textAlign: 'left',
              cursor: 'pointer',
            }}
          >
            <div>
              <strong>
                {candidate.source_cpse} · {candidate.source_code}
              </strong>
              <span>{candidate.source_description}</span>
            </div>
            <b>{formatPercent(candidate.scores.final_score, 0)}</b>
          </button>
        ))
      )}
    </div>
  )
}

export default MatchList
