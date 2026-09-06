import { useMemo, useState } from 'react'

type MappingStatus = 'APPROVED' | 'REVIEW'

type Mapping = {
  cpse: string
  materialCode: string
  originalDescription: string
  nmc: string
  commonDescription: string
  category: string
  status: MappingStatus
  score: number
  approvedBy: string
  approvedOn: string
}

const mappings: Mapping[] = [
  {
    cpse: 'IOCL',
    materialCode: '10003741',
    originalDescription: 'SS304 GATE VALVE 2 IN 150 LB FLG',
    nmc: 'MIRA-VAL-000001',
    commonDescription: 'GATE VALVE, SS304, 2 IN, CLASS 150, FLANGED',
    category: 'Valves',
    status: 'APPROVED',
    score: 94,
    approvedBy: 'Data Steward',
    approvedOn: '06 Sep 2026',
  },
  {
    cpse: 'ONGC',
    materialCode: 'VAL-00921',
    originalDescription: 'SS 304 GATE VALVE 50.8MM CLASS 150',
    nmc: 'MIRA-VAL-000001',
    commonDescription: 'GATE VALVE, SS304, 2 IN, CLASS 150, FLANGED',
    category: 'Valves',
    status: 'APPROVED',
    score: 91,
    approvedBy: 'Data Steward',
    approvedOn: '06 Sep 2026',
  },
  {
    cpse: 'BPCL',
    materialCode: 'BV-004821',
    originalDescription: 'STAINLESS STEEL GATE VALVE 2"',
    nmc: 'MIRA-VAL-000001',
    commonDescription: 'GATE VALVE, SS304, 2 IN, CLASS 150, FLANGED',
    category: 'Valves',
    status: 'APPROVED',
    score: 87,
    approvedBy: 'Data Steward',
    approvedOn: '06 Sep 2026',
  },
  {
    cpse: 'NTPC',
    materialCode: 'NT-VAL-1842',
    originalDescription: 'GATE VALVE SS 304 DN50 PN16 FLANGED',
    nmc: 'MIRA-VAL-000002',
    commonDescription: 'GATE VALVE, SS304, DN50, PN16, FLANGED',
    category: 'Valves',
    status: 'APPROVED',
    score: 93,
    approvedBy: 'Data Steward',
    approvedOn: '05 Sep 2026',
  },
  {
    cpse: 'BHEL',
    materialCode: 'BH-VAL-7712',
    originalDescription: 'SS304 GATE VALVE DN50 PN16 FLG',
    nmc: 'MIRA-VAL-000002',
    commonDescription: 'GATE VALVE, SS304, DN50, PN16, FLANGED',
    category: 'Valves',
    status: 'APPROVED',
    score: 90,
    approvedBy: 'Data Steward',
    approvedOn: '05 Sep 2026',
  },
  {
    cpse: 'SAIL',
    materialCode: 'SAIL-FST-0082',
    originalDescription: 'HEX BOLT M16 X 60 MM SS304',
    nmc: 'MIRA-FST-000001',
    commonDescription: 'HEX BOLT, SS304, M16 X 60 MM',
    category: 'Fasteners',
    status: 'APPROVED',
    score: 96,
    approvedBy: 'Data Steward',
    approvedOn: '04 Sep 2026',
  },
  {
    cpse: 'RINL',
    materialCode: 'RINL-BLT-1029',
    originalDescription: 'SS 304 HEXAGONAL BOLT M16X60',
    nmc: 'MIRA-FST-000001',
    commonDescription: 'HEX BOLT, SS304, M16 X 60 MM',
    category: 'Fasteners',
    status: 'APPROVED',
    score: 94,
    approvedBy: 'Data Steward',
    approvedOn: '04 Sep 2026',
  },
  {
    cpse: 'BHEL',
    materialCode: 'BH-EL-22104',
    originalDescription: 'POWER CONNECTOR 415V 32A',
    nmc: 'MIRA-ELC-000001',
    commonDescription: 'POWER CONNECTOR, 415 V, 32 A',
    category: 'Electrical',
    status: 'REVIEW',
    score: 82,
    approvedBy: '—',
    approvedOn: '—',
  },
]

function StatusBadge({ status }: { status: MappingStatus }) {
  return (
    <span
      className={`mapping-status mapping-status-${status.toLowerCase()}`}
    >
      {status === 'APPROVED' ? 'Approved' : 'Review'}
    </span>
  )
}

function MappingDetails({
  mapping,
  onClose,
}: {
  mapping: Mapping
  onClose: () => void
}) {
  return (
    <div className="mapping-detail-panel">
      <div className="mapping-detail-header">
        <div>
          <div className="eyebrow">MATERIAL MAPPING</div>
          <h2>{mapping.materialCode}</h2>
          <p>{mapping.cpse} → {mapping.nmc}</p>
        </div>

        <button className="mapping-close-button" onClick={onClose}>
          ×
        </button>
      </div>

      <div className="mapping-detail-section">
        <div className="mapping-detail-title">
          <h3>Source Material</h3>
          <StatusBadge status={mapping.status} />
        </div>

        <div className="mapping-object-card">
          <div className="mapping-object-label">
            CPSE · {mapping.cpse}
          </div>

          <strong>{mapping.materialCode}</strong>

          <p>{mapping.originalDescription}</p>

          <div className="mapping-object-meta">
            <span>{mapping.category}</span>
          </div>
        </div>
      </div>

      <div className="mapping-arrow">
        <span>Mapped to</span>
        <strong>↓</strong>
      </div>

      <div className="mapping-detail-section">
        <h3>Common Material</h3>

        <div className="mapping-object-card mapping-common-card">
          <div className="mapping-object-label">
            COMMON NATIONAL MATERIAL CODE
          </div>

          <strong>{mapping.nmc}</strong>

          <p>{mapping.commonDescription}</p>

          <div className="mapping-object-meta">
            <span>{mapping.category}</span>
          </div>
        </div>
      </div>

      <div className="mapping-detail-section">
        <h3>Mapping Evidence</h3>

        <div className="mapping-evidence-grid">
          <div>
            <span>Match confidence</span>
            <strong>{mapping.score}%</strong>
          </div>

          <div>
            <span>Mapping type</span>
            <strong>Material equivalence</strong>
          </div>

          <div>
            <span>Source identity</span>
            <strong>Preserved</strong>
          </div>

          <div>
            <span>Canonical record</span>
            <strong>
              {mapping.status === 'APPROVED'
                ? 'Approved'
                : 'Pending review'}
            </strong>
          </div>
        </div>
      </div>

      <div className="mapping-detail-section">
        <h3>Governance</h3>

        <div className="mapping-governance-row">
          <span>Status</span>
          <StatusBadge status={mapping.status} />
        </div>

        <div className="mapping-governance-row">
          <span>Approved by</span>
          <strong>{mapping.approvedBy}</strong>
        </div>

        <div className="mapping-governance-row">
          <span>Approved on</span>
          <strong>{mapping.approvedOn}</strong>
        </div>
      </div>

      <div className="mapping-detail-actions">
        <button className="mapping-secondary-button">
          View Common Material
        </button>

        <button className="mapping-primary-button">
          Export Mapping
        </button>
      </div>
    </div>
  )
}

export default function Mappings() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All Categories')
  const [status, setStatus] = useState('All Statuses')
  const [selected, setSelected] = useState<Mapping | null>(null)

  const filteredMappings = useMemo(() => {
    const query = search.trim().toLowerCase()

    return mappings.filter((mapping) => {
      const matchesSearch =
        !query ||
        mapping.cpse.toLowerCase().includes(query) ||
        mapping.materialCode.toLowerCase().includes(query) ||
        mapping.nmc.toLowerCase().includes(query) ||
        mapping.originalDescription.toLowerCase().includes(query) ||
        mapping.commonDescription.toLowerCase().includes(query)

      const matchesCategory =
        category === 'All Categories' ||
        mapping.category === category

      const matchesStatus =
        status === 'All Statuses' ||
        mapping.status === status

      return matchesSearch && matchesCategory && matchesStatus
    })
  }, [search, category, status])

  const approved = mappings.filter(
    (mapping) => mapping.status === 'APPROVED',
  ).length

  const review = mappings.filter(
    (mapping) => mapping.status === 'REVIEW',
  ).length

  const commonCodes = new Set(mappings.map((mapping) => mapping.nmc)).size

  return (
    <div className="page">
      <div className="page-header mapping-page-header">
        <div>
          <div className="eyebrow">CPSE → COMMON MASTER</div>
          <h1>Mappings</h1>
          <p>
            Track mappings between CPSE material codes and common national
            material records.
          </p>
        </div>

        <button className="mapping-export-all-button">
          Export Approved Mappings
        </button>
      </div>

      <div className="mapping-summary">
        <div>
          <span>Total Mappings</span>
          <strong>{mappings.length}</strong>
        </div>

        <div>
          <span>Approved</span>
          <strong>{approved}</strong>
        </div>

        <div>
          <span>Common Codes</span>
          <strong>{commonCodes}</strong>
        </div>

        <div>
          <span>Pending Review</span>
          <strong>{review}</strong>
        </div>
      </div>

      <div className="mapping-info-banner">
        <div className="mapping-info-icon">i</div>

        <div>
          <strong>Original CPSE codes are retained</strong>
          <p>
            MIRA creates a common material mapping without replacing the
            source-system material identity.
          </p>
        </div>
      </div>

      <div className="mapping-card">
        <div className="mapping-toolbar">
          <input
            className="mapping-search"
            type="text"
            placeholder="Search CPSE, material code, description or NMC..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />

          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option>All Categories</option>
            <option>Valves</option>
            <option>Fasteners</option>
            <option>Electrical</option>
          </select>

          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option>All Statuses</option>
            <option value="APPROVED">Approved</option>
            <option value="REVIEW">Review</option>
          </select>
        </div>

        <div className="mapping-table-wrapper">
          <table className="mapping-table">
            <thead>
              <tr>
                <th>CPSE</th>
                <th>Original Material Code</th>
                <th>Original Description</th>
                <th>Common National Code</th>
                <th>Category</th>
                <th>Confidence</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {filteredMappings.map((mapping) => (
                <tr
                  key={`${mapping.cpse}-${mapping.materialCode}`}
                  onClick={() => setSelected(mapping)}
                >
                  <td>
                    <strong className="mapping-cpse">
                      {mapping.cpse}
                    </strong>
                  </td>

                  <td>
                    <span className="mapping-code">
                      {mapping.materialCode}
                    </span>
                  </td>

                  <td className="mapping-description">
                    {mapping.originalDescription}
                  </td>

                  <td>
                    <span className="mapping-nmc">
                      {mapping.nmc}
                    </span>
                  </td>

                  <td>{mapping.category}</td>

                  <td>
                    <span
                      className={`mapping-confidence ${
                        mapping.score >= 90
                          ? 'mapping-confidence-high'
                          : 'mapping-confidence-medium'
                      }`}
                    >
                      {mapping.score}%
                    </span>
                  </td>

                  <td>
                    <StatusBadge status={mapping.status} />
                  </td>
                </tr>
              ))}

              {filteredMappings.length === 0 && (
                <tr>
                  <td colSpan={7} className="mapping-empty">
                    No mappings match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mapping-footer">
          Showing {filteredMappings.length} of {mappings.length} demo mappings
        </div>
      </div>

      {selected && (
        <div
          className="mapping-detail-overlay"
          onClick={() => setSelected(null)}
        >
          <div
            className="mapping-detail-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <MappingDetails
              mapping={selected}
              onClose={() => setSelected(null)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
