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
]

function ScoreGrid({ scores }: ScoreGridProps) {
  return (
    <div className="score-grid">
      {SCORE_LABELS.map(([key, label]) => (
        <div key={key}>
          <span>{label}</span>
          <strong>{formatPercent(scores[key], 0)}</strong>
        </div>
      ))}
    </div>
  )
}

export default ScoreGrid
