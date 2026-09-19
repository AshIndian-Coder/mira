import type { MatchScores } from '../../lib/api'
import { formatPercent } from '../../lib/api'

type ScoreGridProps = {
  scores: MatchScores
}

const SCORE_LABELS: Array<[keyof MatchScores, string]> = [
  ['text_similarity', 'Text similarity'],
  ['semantic_similarity', 'Semantic similarity'],
  ['specification_similarity', 'Specification similarity'],
  ['material_grade_similarity', 'Grade similarity'],
  ['other_attributes_similarity', 'Other attributes'],
]

function ScoreGrid({ scores }: ScoreGridProps) {
  return (
    <div className="score-grid">
      {SCORE_LABELS.map(([key, label]) => {
        const val = Math.round((scores[key] ?? 0) * 100)
        return (
          <div key={key}>
            <span>{label}</span>
            <strong>{formatPercent(scores[key], 0)}</strong>
            <div className="cpse-bar-track" style={{ height: '4px', marginTop: '6px' }}>
              <div
                className="cpse-bar"
                style={{
                  width: `${val}%`,
                  background: val >= 80 ? '#10b981' : val >= 50 ? '#f59e0b' : '#64748b',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default ScoreGrid
