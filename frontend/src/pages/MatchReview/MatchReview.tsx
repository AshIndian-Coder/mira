import { useCallback, useEffect, useState } from 'react'

import MatchComparison from '../../components/Matching/MatchComparison'
import MatchList from '../../components/Matching/MatchList'
import { api, type Candidate } from '../../lib/api'

function MatchReview() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [totalPending, setTotalPending] = useState(0)
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadQueue = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.reviewQueue()
      setTotalPending(response.total_pending)
      setCandidates(response.queue)
      setSelected((current) => {
        if (response.queue.length === 0) return null
        if (current && response.queue.some((item) => item.id === current.id)) {
          return response.queue.find((item) => item.id === current.id) ?? response.queue[0]
        }
        return response.queue[0]
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load review queue')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadQueue()
  }, [loadQueue])

  const handleAction = async (action: 'APPROVE' | 'REJECT') => {
    if (!selected) return

    try {
      setActing(true)
      setError(null)
      await api.reviewAction(selected.id, action)
      await loadQueue()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review action failed')
    } finally {
      setActing(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <span className="eyebrow">AI-ASSISTED VALIDATION</span>
          <h1>Match Review</h1>
          <p>Review candidate material equivalences before harmonization.</p>
        </div>
        <span className="review-count">
          {loading ? '…' : `${totalPending} pending`}
        </span>
      </div>

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Error</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <div className="review-layout">
        <MatchList
          candidates={candidates}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
          loading={loading}
        />
        <MatchComparison
          candidate={selected}
          onApprove={() => handleAction('APPROVE')}
          onReject={() => handleAction('REJECT')}
          acting={acting}
        />
      </div>
    </div>
  )
}

export default MatchReview
