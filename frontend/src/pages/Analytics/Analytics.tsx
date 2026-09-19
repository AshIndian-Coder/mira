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

const PIE_COLORS: Record<string, string> = {
  Approved: '#10b981',
  'Pending Review': '#f59e0b',
  Rejected: '#ef4444',
}

const CPSE_BAR_COLORS = ['#334155', '#475569', '#64748b', '#0f172a', '#1e293b', '#94a3b8']
const CONFIDENCE_BAR_COLORS = ['#4f46e5', '#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe']
const CATEGORY_COLORS = ['#1e293b', '#4f46e5', '#0284c7', '#10b981', '#f59e0b', '#8b5cf6', '#64748b']

type TooltipPayloadItem = {
  name?: string
  value?: number | string
  color?: string
}

function CustomChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string
}) {
  if (active && payload && payload.length) {
    const item = payload[0]
    return (
      <div className="recharts-custom-tooltip">
        {label && <div className="tooltip-label">{label}</div>}
        <div className="tooltip-value-row">
          {item.color && (
            <span
              className="tooltip-color-dot"
              style={{ background: item.color }}
            />
          )}
          <span className="tooltip-key">{item.name ? `${item.name}: ` : ''}</span>
          <span className="tooltip-val">
            {typeof item.value === 'number' ? item.value.toLocaleString() : item.value}
          </span>
        </div>
      </div>
    )
  }
  return null
}

export default function Analytics() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [cpseData, setCpseData] = useState<CpseBreakdown[]>([])
  const [categoryData, setCategoryData] = useState<CategoryDistribution[]>([])
  const [scoreData, setScoreData] = useState<ScoreBucket[]>([])
  const [qualityData, setQualityData] = useState<import('../../lib/api').DataQualityMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const [overviewRes, cpseRes, categoryRes, scoreRes, qualityRes] = await Promise.all([
          api.analyticsOverview(),
          api.analyticsByCpse(),
          api.analyticsCategories(),
          api.analyticsScores(),
          api.analyticsDataQuality(),
        ])
        setOverview(overviewRes)
        setCpseData(cpseRes.cpse_breakdown)
        setCategoryData(categoryRes.category_distribution)
        setScoreData(scoreRes.score_histogram)
        setQualityData(qualityRes)
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
    <div className="page analytics-page">
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
          <small>Human-approved relationships</small>
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
            {loading ? (
              <div className="dashboard-empty-state">Loading CPSE metrics…</div>
            ) : cpseChartData.length === 0 ? (
              <div className="dashboard-empty-state">No CPSE data yet. Upload materials first.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cpseChartData} margin={{ top: 16, right: 20, left: -10, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#edf2f7" />
                  <XAxis
                    dataKey="cpse"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tickLine={false}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tickLine={false}
                  />
                  <Tooltip
                    content={<CustomChartTooltip />}
                    cursor={{ fill: 'rgba(241, 245, 249, 0.7)', rx: 6, ry: 6 }}
                    isAnimationActive={true}
                    animationDuration={250}
                    animationEasing="ease-out"
                  />
                  <Bar
                    dataKey="materials"
                    name="Materials"
                    maxBarSize={44}
                    radius={[6, 6, 0, 0]}
                    animationDuration={600}
                  >
                    {cpseChartData.map((entry, index) => (
                      <Cell
                        key={entry.cpse}
                        fill={CPSE_BAR_COLORS[index % CPSE_BAR_COLORS.length]}
                      />
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
            {loading ? (
              <div className="dashboard-empty-state">Loading disposition data…</div>
            ) : harmonizationData.length === 0 ? (
              <div className="dashboard-empty-state">No candidate disposition data available yet.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={harmonizationData}
                    cx="50%"
                    cy="44%"
                    innerRadius={58}
                    outerRadius={84}
                    paddingAngle={4}
                    dataKey="value"
                    nameKey="name"
                    animationDuration={600}
                  >
                    {harmonizationData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={PIE_COLORS[entry.name] ?? '#64748b'}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    content={<CustomChartTooltip />}
                    isAnimationActive={true}
                    animationDuration={250}
                    animationEasing="ease-out"
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(val) => (
                      <span style={{ color: '#334155', fontSize: '11.5px', fontWeight: 600 }}>
                        {val}
                      </span>
                    )}
                  />
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
            {loading ? (
              <div className="dashboard-empty-state">Loading category metrics…</div>
            ) : categoryChartData.length === 0 ? (
              <div className="dashboard-empty-state">No category data yet.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categoryChartData}
                    cx="50%"
                    cy="44%"
                    innerRadius={50}
                    outerRadius={78}
                    paddingAngle={3}
                    dataKey="value"
                    nameKey="name"
                    animationDuration={600}
                  >
                    {categoryChartData.map((entry, index) => (
                      <Cell
                        key={entry.name}
                        fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    content={<CustomChartTooltip />}
                    isAnimationActive={true}
                    animationDuration={250}
                    animationEasing="ease-out"
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={44}
                    wrapperStyle={{ fontSize: 11 }}
                    formatter={(val) => (
                      <span style={{ color: '#334155', fontSize: '11px', fontWeight: 500 }}>
                        {val}
                      </span>
                    )}
                  />
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
            {loading ? (
              <div className="dashboard-empty-state">Loading score buckets…</div>
            ) : confidenceData.every((row) => row.count === 0) ? (
              <div className="dashboard-empty-state">No score data yet. Run matching first.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={confidenceData} margin={{ top: 16, right: 20, left: -10, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#edf2f7" />
                  <XAxis
                    dataKey="range"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tickLine={false}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tickLine={false}
                  />
                  <Tooltip
                    content={<CustomChartTooltip />}
                    cursor={{ fill: 'rgba(241, 245, 249, 0.7)', rx: 6, ry: 6 }}
                    isAnimationActive={true}
                    animationDuration={250}
                    animationEasing="ease-out"
                  />
                  <Bar
                    dataKey="count"
                    name="Candidates"
                    maxBarSize={38}
                    radius={[6, 6, 0, 0]}
                    animationDuration={600}
                  >
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

      {/* Data Quality & Master Attribute Completeness */}
      <section className="analytics-card" style={{ marginTop: '20px' }}>
        <div className="analytics-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2>Data Quality & Attribute Completeness</h2>
            <p>Specification parsing yield, critical attribute availability, and master data health across CPSEs.</p>
          </div>
          {qualityData && (
            <div style={{ display: 'flex', gap: '12px' }}>
              <div style={{ padding: '4px 10px', borderRadius: '6px', background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', fontSize: '11.5px', fontWeight: 600 }}>
                Spec Yield: {formatPercent(qualityData.parsed_specs_rate, 1)}
              </div>
              <div style={{ padding: '4px 10px', borderRadius: '6px', background: '#f8fafc', border: '1px solid #e2e8f0', color: '#334155', fontSize: '11.5px', fontWeight: 600 }}>
                Health Score: {formatPercent(qualityData.completeness_score, 1)}
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '16px 22px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '18px' }}>
            <div style={{ padding: '12px 14px', borderRadius: '8px', background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Parsed Specifications</span>
              <strong style={{ fontSize: '18px', color: '#0f172a', fontWeight: 700 }}>
                {loading || !qualityData ? '—' : formatNumber(qualityData.with_parsed_specs)}
              </strong>
              <small style={{ fontSize: '10.5px', color: '#94a3b8', display: 'block' }}>
                of {formatNumber(qualityData?.total_materials ?? 0)} records
              </small>
            </div>
            <div style={{ padding: '12px 14px', borderRadius: '8px', background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Missing Material Grade</span>
              <strong style={{ fontSize: '18px', color: '#b91c1c', fontWeight: 700 }}>
                {loading || !qualityData ? '—' : formatNumber(qualityData.missing_material_grade)}
              </strong>
              <small style={{ fontSize: '10.5px', color: '#94a3b8', display: 'block' }}>
                {qualityData && qualityData.total_materials > 0 ? formatPercent(qualityData.missing_material_grade / qualityData.total_materials, 1) : '0%'} unpopulated
              </small>
            </div>
            <div style={{ padding: '12px 14px', borderRadius: '8px', background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Missing Dimensions</span>
              <strong style={{ fontSize: '18px', color: '#b91c1c', fontWeight: 700 }}>
                {loading || !qualityData ? '—' : formatNumber(qualityData.missing_dimensions)}
              </strong>
              <small style={{ fontSize: '10.5px', color: '#94a3b8', display: 'block' }}>
                {qualityData && qualityData.total_materials > 0 ? formatPercent(qualityData.missing_dimensions / qualityData.total_materials, 1) : '0%'} unpopulated
              </small>
            </div>
            <div style={{ padding: '12px 14px', borderRadius: '8px', background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Missing Pressure Rating</span>
              <strong style={{ fontSize: '18px', color: '#b91c1c', fontWeight: 700 }}>
                {loading || !qualityData ? '—' : formatNumber(qualityData.missing_pressure_rating)}
              </strong>
              <small style={{ fontSize: '10.5px', color: '#94a3b8', display: 'block' }}>
                {qualityData && qualityData.total_materials > 0 ? formatPercent(qualityData.missing_pressure_rating / qualityData.total_materials, 1) : '0%'} unpopulated
              </small>
            </div>
          </div>

          {/* Per-CPSE Data Quality Breakdown Table */}
          {qualityData && qualityData.by_cpse_quality.length > 0 && (
            <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontWeight: 600 }}>
                    <th style={{ padding: '10px 14px' }}>CPSE Source</th>
                    <th style={{ padding: '10px 14px' }}>Total Records</th>
                    <th style={{ padding: '10px 14px' }}>Parsed Specifications</th>
                    <th style={{ padding: '10px 14px' }}>Spec Yield Rate</th>
                    <th style={{ padding: '10px 14px' }}>Missing Grade</th>
                    <th style={{ padding: '10px 14px' }}>Missing Dimensions</th>
                    <th style={{ padding: '10px 14px' }}>Missing Pressure</th>
                  </tr>
                </thead>
                <tbody>
                  {qualityData.by_cpse_quality.map((row) => (
                    <tr key={row.cpse} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '9px 14px', fontWeight: 600, color: '#0f172a' }}>{row.cpse}</td>
                      <td style={{ padding: '9px 14px', color: '#334155' }}>{formatNumber(row.total_materials)}</td>
                      <td style={{ padding: '9px 14px', color: '#334155' }}>{formatNumber(row.with_parsed_specs)}</td>
                      <td style={{ padding: '9px 14px', fontWeight: 600, color: row.parsed_specs_rate >= 0.5 ? '#166534' : '#b45309' }}>
                        {formatPercent(row.parsed_specs_rate, 1)}
                      </td>
                      <td style={{ padding: '9px 14px', color: '#64748b' }}>{formatNumber(row.missing_grade)}</td>
                      <td style={{ padding: '9px 14px', color: '#64748b' }}>{formatNumber(row.missing_dimensions)}</td>
                      <td style={{ padding: '9px 14px', color: '#64748b' }}>{formatNumber(row.missing_pressure)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
