import { useEffect, useState } from 'react'

import StatCard from '../../components/Dashboard/StatCard'
import Workflow from '../../components/Dashboard/Workflow'
import { api, formatNumber } from '../../lib/api'

function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState({
    totalMaterials: 0,
    matchesIdentified: 0,
    pendingReview: 0,
    harmonized: 0,
  })

  useEffect(() => {
    let active = true

    async function load() {
      try {
        setLoading(true)
        setError(null)
        const overview = await api.analyticsOverview()
        if (!active) return

        setStats({
          totalMaterials: overview.total_materials,
          matchesIdentified: overview.total_candidate_pairs,
          pendingReview: overview.review_pending,
          harmonized: overview.approved,
        })
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error ? err.message : 'Failed to load dashboard data',
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    load()
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <span className="eyebrow">NATIONAL MATERIAL GOVERNANCE</span>
          <h1>Overview</h1>
          <p>
            Monitor material harmonization across participating CPSEs.
          </p>
        </div>
      </div>

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Backend unavailable</strong>
            <p>{error}. Start the backend on port 8000 and refresh.</p>
          </div>
        </div>
      )}

      <div className="stats-grid">
        <StatCard
          label="Total Materials"
          value={loading ? '—' : formatNumber(stats.totalMaterials)}
          description="Across connected sources"
        />
        <StatCard
          label="Matches Identified"
          value={loading ? '—' : formatNumber(stats.matchesIdentified)}
          description="Candidate relationships"
        />
        <StatCard
          label="Pending Review"
          value={loading ? '—' : formatNumber(stats.pendingReview)}
          description="Require human validation"
        />
        <StatCard
          label="Harmonized"
          value={loading ? '—' : formatNumber(stats.harmonized)}
          description="Approved mappings"
        />
      </div>

      <div className="section-card">
        <div className="section-header">
          <div>
            <h2>Harmonization Workflow</h2>
            <p>Current state of the material standardization pipeline.</p>
          </div>
        </div>
        <Workflow />
      </div>
    </div>
  )
}

export default Dashboard
