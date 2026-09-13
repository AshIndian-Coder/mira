import { useEffect, useState } from 'react'

import StatCard from '../../components/Dashboard/StatCard'
import Workflow from '../../components/Dashboard/Workflow'
import { api, formatNumber, formatPercent, type AnalyticsOverview, type CpseBreakdown, type Mapping } from '../../lib/api'

function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [cpseBreakdown, setCpseBreakdown] = useState<CpseBreakdown[]>([])
  const [mappings, setMappings] = useState<Mapping[]>([])

  useEffect(() => {
    let active = true

    async function load() {
      try {
        setLoading(true)
        setError(null)

        const [overviewData, cpseData, mappingsData] = await Promise.all([
          api.analyticsOverview(),
          api.analyticsByCpse(),
          api.listMappings(),
        ])

        if (!active) return

        setOverview(overviewData)
        setCpseBreakdown(cpseData.cpse_breakdown)
        setMappings(mappingsData.mappings)
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load dashboard data',
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

  const totalMaterials = overview?.total_materials ?? 0
  const cpseCount = overview?.cpse_count ?? 0
  const candidatePairs = overview?.total_candidate_pairs ?? 0
  const pendingReview = overview?.review_pending ?? 0
  const highConfidence = overview?.high_confidence ?? 0
  const approved = overview?.approved ?? 0
  const rejected = overview?.rejected ?? 0
  const automationRate = overview?.automation_rate ?? null
  const mappingCount = mappings.length

  const maxCpseMaterials = Math.max(
    ...cpseBreakdown.map((item) => item.material_count),
    1,
  )

  return (
    <div className="page dashboard-page">
      <div className="page-header dashboard-header">
        <div>
          <span className="eyebrow">NATIONAL MATERIAL GOVERNANCE</span>
          <h1>Overview</h1>
          <p>
            Monitor material harmonization across participating CPSEs.
          </p>
        </div>

        <div className="dashboard-status">
          <span className="dashboard-status-dot" />
          <span>{error ? 'Backend unavailable' : 'System connected'}</span>
        </div>
      </div>

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Dashboard data unavailable</strong>
            <p>{error}. Start the backend on port 8000 and refresh.</p>
          </div>
        </div>
      )}

      <div className="stats-grid dashboard-primary-stats">
        <StatCard
          label="Total Materials"
          value={loading ? '—' : formatNumber(totalMaterials)}
          description="Across connected CPSE sources"
        />
        <StatCard
          label="CPSEs Connected"
          value={loading ? '—' : formatNumber(cpseCount)}
          description="Participating source organisations"
        />
        <StatCard
          label="Candidate Matches"
          value={loading ? '—' : formatNumber(candidatePairs)}
          description="AI-generated candidate relationships"
        />
        <StatCard
          label="Pending Review"
          value={loading ? '—' : formatNumber(pendingReview)}
          description="Require human validation"
        />
      </div>

      <div className="dashboard-secondary-stats">
        <StatCard
          label="High Confidence"
          value={loading ? '—' : formatNumber(highConfidence)}
          description="Resolved by matching engine"
        />
        <StatCard
          label="Approved"
          value={loading ? '—' : formatNumber(approved)}
          description="Human-approved relationships"
        />
        <StatCard
          label="Rejected"
          value={loading ? '—' : formatNumber(rejected)}
          description="Rejected candidate relationships"
        />
        <StatCard
          label="Automation Rate"
          value={
            loading
              ? '—'
              : automationRate === null
                ? '—'
                : formatPercent(automationRate)
          }
          description="High-confidence / actionable pairs"
        />
      </div>

      <div className="section-card dashboard-pipeline">
        <div className="section-header">
          <div>
            <h2>Harmonization Pipeline</h2>
            <p>Current state of the material standardization workflow.</p>
          </div>
        </div>

        <Workflow
          totalMaterials={totalMaterials}
          candidatePairs={candidatePairs}
          pendingReview={pendingReview}
          approved={approved}
          mappings={mappingCount}
          loading={loading}
        />
      </div>

      <div className="dashboard-lower-grid">
        <div className="section-card">
          <div className="section-header">
            <div>
              <h2>CPSE Coverage</h2>
              <p>Material volume and candidate involvement by source.</p>
            </div>
          </div>

          {loading ? (
            <div className="dashboard-empty-state">Loading CPSE data…</div>
          ) : cpseBreakdown.length === 0 ? (
            <div className="dashboard-empty-state">
              No CPSE material data available yet.
            </div>
          ) : (
            <div className="cpse-list">
              {cpseBreakdown.map((item) => (
                <div className="cpse-row" key={item.cpse}>
                  <div className="cpse-row-header">
                    <strong>{item.cpse}</strong>
                    <span>
                      {formatNumber(item.material_count)} materials
                    </span>
                  </div>

                  <div className="cpse-bar-track">
                    <div
                      className="cpse-bar"
                      style={{
                        width: `${(item.material_count / maxCpseMaterials) * 100}%`,
                      }}
                    />
                  </div>

                  <small>
                    {formatNumber(item.candidate_pair_involvements)} candidate
                    {item.candidate_pair_involvements === 1 ? '' : 's'} involved
                  </small>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="section-card">
          <div className="section-header">
            <div>
              <h2>Match Outcomes</h2>
              <p>Current disposition of candidate relationships.</p>
            </div>
          </div>

          <div className="outcome-list">
            <div className="outcome-row">
              <div>
                <span className="outcome-indicator outcome-high" />
                <strong>High Confidence</strong>
              </div>
              <span>{loading ? '—' : formatNumber(highConfidence)}</span>
            </div>

            <div className="outcome-row">
              <div>
                <span className="outcome-indicator outcome-review" />
                <strong>Pending Review</strong>
              </div>
              <span>{loading ? '—' : formatNumber(pendingReview)}</span>
            </div>

            <div className="outcome-row">
              <div>
                <span className="outcome-indicator outcome-approved" />
                <strong>Approved</strong>
              </div>
              <span>{loading ? '—' : formatNumber(approved)}</span>
            </div>

            <div className="outcome-row">
              <div>
                <span className="outcome-indicator outcome-rejected" />
                <strong>Rejected</strong>
              </div>
              <span>{loading ? '—' : formatNumber(rejected)}</span>
            </div>
          </div>

          <div className="dashboard-mapping-summary">
            <span>Common mappings</span>
            <strong>{loading ? '—' : formatNumber(mappingCount)}</strong>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
