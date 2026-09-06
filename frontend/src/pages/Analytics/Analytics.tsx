import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const cpseData = [
  { cpse: 'IOCL', materials: 12842 },
  { cpse: 'ONGC', materials: 9614 },
  { cpse: 'BPCL', materials: 7426 },
  { cpse: 'NTPC', materials: 8391 },
  { cpse: 'SAIL', materials: 2941 },
  { cpse: 'BHEL', materials: 2087 },
]

const harmonizationData = [
  { name: 'Harmonized', value: 6184 },
  { name: 'Pending Review', value: 326 },
  { name: 'Unmatched', value: 1472 },
]

const categoryData = [
  { name: 'Valves', value: 12480 },
  { name: 'Fasteners', value: 8960 },
  { name: 'Electrical', value: 7140 },
  { name: 'Pipes & Fittings', value: 6320 },
  { name: 'Bearings', value: 4210 },
  { name: 'Other', value: 4191 },
]

const matchingTrend = [
  { month: 'Apr', identified: 1180, approved: 760 },
  { month: 'May', identified: 1460, approved: 940 },
  { month: 'Jun', identified: 1720, approved: 1210 },
  { month: 'Jul', identified: 1960, approved: 1380 },
  { month: 'Aug', identified: 2310, approved: 1610 },
  { month: 'Sep', identified: 2412, approved: 1840 },
]

const confidenceData = [
  { range: '90–100%', count: 4210 },
  { range: '80–89%', count: 2630 },
  { range: '70–79%', count: 1240 },
  { range: '<70%', count: 662 },
]

const PIE_COLORS = ['#172033', '#4f6f95', '#8da2bc']

const CPSE_BAR_COLORS = [
  '#315B8A',
  '#4779A8',
  '#5E91B8',
  '#729FBE',
  '#879FB8',
  '#9BAFC2',
]

const CONFIDENCE_BAR_COLORS = [
  '#315B8A',
  '#5E91B8',
  '#879FB8',
  '#B0BBC7',
]

const CATEGORY_COLORS = [
  '#315B8A',
  '#4779A8',
  '#5E91B8',
  '#729FBE',
  '#879FB8',
  '#9BAFC2',
]

export default function Analytics() {
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

        <div className="analytics-filters">
          <select defaultValue="all">
            <option value="all">All CPSEs</option>
            <option value="IOCL">IOCL</option>
            <option value="ONGC">ONGC</option>
            <option value="BPCL">BPCL</option>
            <option value="NTPC">NTPC</option>
            <option value="SAIL">SAIL</option>
            <option value="BHEL">BHEL</option>
          </select>

          <select defaultValue="all">
            <option value="all">All Categories</option>
            <option value="valves">Valves</option>
            <option value="fasteners">Fasteners</option>
            <option value="electrical">Electrical</option>
            <option value="pipes">Pipes & Fittings</option>
          </select>

          <select defaultValue="6m">
            <option value="30d">Last 30 days</option>
            <option value="3m">Last 3 months</option>
            <option value="6m">Last 6 months</option>
            <option value="1y">Last year</option>
          </select>
        </div>
      </div>

      <section className="analytics-kpis">
        <div className="analytics-kpi">
          <span>Total Materials</span>
          <strong>43,301</strong>
          <small>Across 6 CPSE sources</small>
        </div>

        <div className="analytics-kpi">
          <span>Matches Identified</span>
          <strong>8,742</strong>
          <small>Candidate relationships</small>
        </div>

        <div className="analytics-kpi">
          <span>Automation Rate</span>
          <strong>72.4%</strong>
          <small>Cases resolved without review</small>
        </div>

        <div className="analytics-kpi">
          <span>Harmonized</span>
          <strong>6,184</strong>
          <small>Approved common records</small>
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
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={cpseData}
                margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="cpse" />
                <YAxis />
                <Tooltip />

                <Bar
                  dataKey="materials"
                  name="Materials"
                  radius={[3, 3, 0, 0]}
                >
                  {cpseData.map((entry, index) => (
                    <Cell
                      key={entry.cpse}
                      fill={CPSE_BAR_COLORS[index]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="analytics-card">
          <div className="analytics-card-header">
            <div>
              <h2>Harmonization Status</h2>
              <p>Current state of material records.</p>
            </div>
          </div>

          <div className="chart-container chart-container-donut">
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
                    <Cell
                      key={entry.name}
                      fill={PIE_COLORS[index % PIE_COLORS.length]}
                    />
                  ))}
                </Pie>

                <Tooltip />
                <Legend verticalAlign="bottom" height={36} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="analytics-grid analytics-grid-bottom">
        <div className="analytics-card analytics-card-wide">
          <div className="analytics-card-header">
            <div>
              <h2>Matching Activity</h2>
              <p>Candidate matches identified versus approved mappings.</p>
            </div>
          </div>

          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={matchingTrend}
                margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Legend />

                <Line
                  type="monotone"
                  dataKey="identified"
                  name="Matches identified"
                  stroke="#315B8A"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />

                <Line
                  type="monotone"
                  dataKey="approved"
                  name="Approved mappings"
                  stroke="#729FBE"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="analytics-card">
          <div className="analytics-card-header">
            <div>
              <h2>Material Categories</h2>
              <p>Distribution across the current master.</p>
            </div>
          </div>

          <div className="chart-container chart-container-donut">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={categoryData}
                  cx="50%"
                  cy="45%"
                  innerRadius={55}
                  outerRadius={88}
                  paddingAngle={1}
                  dataKey="value"
                  nameKey="name"
                >
                  {categoryData.map((entry, index) => (
                    <Cell
                      key={entry.name}
                      fill={CATEGORY_COLORS[index]}
                    />
                  ))}
                </Pie>

                <Tooltip />

                <Legend
                  verticalAlign="bottom"
                  height={50}
                  wrapperStyle={{ fontSize: 11 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="analytics-grid analytics-grid-bottom">
        <div className="analytics-card">
          <div className="analytics-card-header">
            <div>
              <h2>Match Confidence</h2>
              <p>Distribution of candidate match scores.</p>
            </div>
          </div>

          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={confidenceData}
                margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="range" />
                <YAxis />
                <Tooltip />

                <Bar
                  dataKey="count"
                  name="Candidates"
                  radius={[3, 3, 0, 0]}
                >
                  {confidenceData.map((entry, index) => (
                    <Cell
                      key={entry.range}
                      fill={CONFIDENCE_BAR_COLORS[index]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="analytics-card analytics-insight-card">
          <div className="analytics-card-header">
            <div>
              <h2>Governance Summary</h2>
              <p>Current review workload.</p>
            </div>
          </div>

          <div className="insight-list">
            <div className="insight-row">
              <span>Pending human review</span>
              <strong>326</strong>
            </div>

            <div className="insight-row">
              <span>Approved common materials</span>
              <strong>6,184</strong>
            </div>

            <div className="insight-row">
              <span>CPSE source mappings</span>
              <strong>9</strong>
            </div>

            <div className="insight-row">
              <span>High-confidence candidates</span>
              <strong>4,210</strong>
            </div>
          </div>

          <div className="analytics-note">
            Analytics are based on the current prototype material master.
            Production values will be supplied by the harmonization APIs.
          </div>
        </div>
      </section>
    </main>
  )
}
