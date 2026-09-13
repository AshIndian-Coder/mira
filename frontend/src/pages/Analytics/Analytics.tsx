import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  api,
  formatNumber,
  formatPercent,
  type AnalyticsOverview,
  type CategoryDistribution,
  type CpseBreakdown,
  type ScoreBucket,
} from '../../lib/api'

const PIE_COLORS = ['#172033', '#4f6f95', '#8da2bc']
const CPSE_BAR_COLORS = ['#315B8A', '#4779A8', '#5E91B8', '#729FBE', '#879FB8', '#9BAFC2']
const CONFIDENCE_BAR_COLORS = ['#315B8A', '#5E91B8', '#879FB8', '#B0BBC7']
const CATEGORY_COLORS = ['#315B8A', '#4779A8', '#5E91B8', '#729FBE', '#879FB8', '#9BAFC2']

export default function Analytics() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [cpseData, setCpseData] = useState<CpseBreakdown[]>([])
  const [categoryData, setCategoryData] = useState<CategoryDistribution[]>([])
  const [scoreData, setScoreData] = useState<ScoreBucket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const [overviewRes, cpseRes, categoryRes, scoreRes] = await Promise.all([
          api.analyticsOverview(),
          api.analyticsByCpse(),
          api.analyticsCategories(),
          api.analyticsScores(),
        ])
        setOverview(overviewRes)
        setCpseData(cpseRes.cpse_breakdown)
        setCategoryData(categoryRes.category_distribution)
        setScoreData(scoreRes.score_histogram)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load analytics')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const harmonizationData = useMemo(() => {
    if (!overview) return []
    return [
      { name: 'Approved', value: overview.approved },
      { name: 'Pending Review', value: overview.review_pending },
      { name: 'Rejected', value: overview.rejected },
    ].filter((item) => item.value > 0)
  }, [overview])

  const confidenceData = useMemo(() => {
    return scoreData.map((bucket) => ({
      range: bucket.bucket,
      count: bucket.count,
    }))
  }, [scoreData])

  const cpseChartData = cpseData.map((row) => ({
    cpse: row.cpse,
    materials: row.material_count,
  }))

  const categoryChartData = categoryData.map((row) => ({
    name: row.category,
    value: row.count,
  }))

  return (
    <main className="page-content analytics-page">
      <div className="page-header analytics-header">
        <div>
          <div className="eyebrow">MATERIAL INTELLIGENCE</div>
          <h1>Analytics</h1>
          <p>
            Monitor material quality, matching performance and harmonization
            progress across participating CPSEs.
          </p>
        </div>
      </div>

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Backend unavailable</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <section className="analytics-kpis">
        <div className="analytics-kpi">
          <span>Total Materials</span>
          <strong>{loading || !overview ? '—' : formatNumber(overview.total_materials)}</strong>
          <small>Across {overview?.cpse_count ?? 0} CPSE sources</small>
        </div>
        <div className="analytics-kpi">
          <span>Matches Identified</span>
          <strong>
            {loading || !overview ? '—' : formatNumber(overview.total_candidate_pairs)}
          </strong>
          <small>Candidate relationships</small>
        </div>
        <div className="analytics-kpi">
          <span>Automation Rate</span>
          <strong>
            {loading || !overview || overview.automation_rate == null
              ? '—'
              : formatPercent(overview.automation_rate, 1)}
          </strong>
          <small>Cases resolved without review</small>
        </div>
        <div className="analytics-kpi">
          <span>Approved</span>
          <strong>{loading || !overview ? '—' : formatNumber(overview.approved)}</strong>
          <small>Human-approved candidate relationships</small>
        </div>
      </section>

      <section className="analytics-grid analytics-grid-top">
        <div className="analytics-card analytics-card-wide">
          <div className="analytics-card-header">
            <div>
              <h2>Materials by CPSE</h2>
              <p>Material records currently represented in the master.</p>
            </div>
          </div>
          <div className="chart-container">
            {cpseChartData.length === 0 ? (
              <p style={{ padding: '1rem' }}>No CPSE data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cpseChartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="cpse" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="materials" name="Materials" radius={[3, 3, 0, 0]}>
                    {cpseChartData.map((entry, index) => (
                      <Cell key={entry.cpse} fill={CPSE_BAR_COLORS[index % CPSE_BAR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="analytics-card">
          <div className="analytics-card-header">
            <div>
              <h2>Candidate Disposition</h2>
              <p>Current disposition of candidate relationships.</p>
            </div>
          </div>
          <div className="chart-container chart-container-donut">
            {harmonizationData.length === 0 ? (
              <p style={{ padding: '1rem' }}>No harmonization data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={harmonizationData}
                    cx="50%"
                    cy="48%"
                    innerRadius={65}
                    outerRadius={95}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                  >
                    {harmonizationData.map((entry, index) => (
                      <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend verticalAlign="bottom" height={36} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </section>

      <section className="analytics-grid analytics-grid-bottom">
        <div className="analytics-card">
          <div className="analytics-card-header">
            <div>
              <h2>Material Categories</h2>
              <p>Distribution across the current master.</p>
            </div>
          </div>
          <div className="chart-container chart-container-donut">
            {categoryChartData.length === 0 ? (
              <p style={{ padding: '1rem' }}>No category data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryChartData}
                    cx="50%"
                    cy="45%"
                    innerRadius={55}
                    outerRadius={88}
                    paddingAngle={1}
                    dataKey="value"
                    nameKey="name"
                  >
                    {categoryChartData.map((entry, index) => (
                      <Cell key={entry.name} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend verticalAlign="bottom" height={50} wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="analytics-card">
          <div className="analytics-card-header">
            <div>
              <h2>Candidate Score Distribution</h2>
              <p>Distribution of final candidate match scores.</p>
            </div>
          </div>
          <div className="chart-container">
            {confidenceData.every((row) => row.count === 0) ? (
              <p style={{ padding: '1rem' }}>No score data yet. Run matching first.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={confidenceData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="range" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" name="Candidates" radius={[3, 3, 0, 0]}>
                    {confidenceData.map((entry, index) => (
                      <Cell
                        key={entry.range}
                        fill={CONFIDENCE_BAR_COLORS[index % CONFIDENCE_BAR_COLORS.length]}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}
