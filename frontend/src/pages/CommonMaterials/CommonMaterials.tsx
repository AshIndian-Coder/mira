import { useMemo, useState } from 'react'

type ApprovalStatus = 'APPROVED' | 'REVIEW'

type SourceMaterial = {
  cpse: string
  code: string
  description: string
}

type CommonMaterial = {
  nmc: string
  description: string
  category: string
  material: string
  size: string
  pressure: string
  status: ApprovalStatus
  sourceCount: number
  sources: SourceMaterial[]
}

const commonMaterials: CommonMaterial[] = [
  {
    nmc: 'MIRA-VAL-000001',
    description: 'GATE VALVE, SS304, 2 IN, CLASS 150, FLANGED',
    category: 'Valves',
    material: 'SS304',
    size: '2 inch',
    pressure: 'Class 150',
    status: 'APPROVED',
    sourceCount: 3,
    sources: [
      {
        cpse: 'IOCL',
        code: '10003741',
        description: 'SS304 GATE VALVE 2 IN 150 LB FLG',
      },
      {
        cpse: 'ONGC',
        code: 'VAL-00921',
        description: 'SS 304 GATE VALVE 50.8MM CLASS 150',
      },
      {
        cpse: 'BPCL',
        code: 'BV-004821',
        description: 'STAINLESS STEEL GATE VALVE 2"',
      },
    ],
  },
  {
    nmc: 'MIRA-VAL-000002',
    description: 'GATE VALVE, SS304, DN50, PN16, FLANGED',
    category: 'Valves',
    material: 'SS304',
    size: 'DN50',
    pressure: 'PN16',
    status: 'APPROVED',
    sourceCount: 2,
    sources: [
      {
        cpse: 'NTPC',
        code: 'NT-VAL-1842',
        description: 'GATE VALVE SS 304 DN50 PN16 FLANGED',
      },
      {
        cpse: 'BHEL',
        code: 'BH-VAL-7712',
        description: 'SS304 GATE VALVE DN50 PN16 FLG',
      },
    ],
  },
  {
    nmc: 'MIRA-FST-000001',
    description: 'HEX BOLT, SS304, M16 X 60 MM',
    category: 'Fasteners',
    material: 'SS304',
    size: 'M16 × 60 mm',
    pressure: '—',
    status: 'APPROVED',
    sourceCount: 2,
    sources: [
      {
        cpse: 'SAIL',
        code: 'SAIL-FST-0082',
        description: 'HEX BOLT M16 X 60 MM SS304',
      },
      {
        cpse: 'RINL',
        code: 'RINL-BLT-1029',
        description: 'SS 304 HEXAGONAL BOLT M16X60',
      },
    ],
  },
  {
    nmc: 'MIRA-ELC-000001',
    description: 'POWER CONNECTOR, 415 V, 32 A',
    category: 'Electrical',
    material: 'Copper',
    size: '32 A',
    pressure: '415 V',
    status: 'REVIEW',
    sourceCount: 2,
    sources: [
      {
        cpse: 'BHEL',
        code: 'BH-EL-22104',
        description: 'POWER CONNECTOR 415V 32A',
      },
      {
        cpse: 'NTPC',
        code: 'NT-EL-09182',
        description: 'POWER CONNECTOR 32 AMP 415 VOLT',
      },
    ],
  },
]

function ApprovalBadge({ status }: { status: ApprovalStatus }) {
  return (
    <span
      className={`common-status common-status-${status.toLowerCase()}`}
    >
      {status === 'APPROVED' ? 'Approved' : 'Review'}
    </span>
  )
}

function CommonMaterialDetails({
  material,
  onClose,
}: {
  material: CommonMaterial
  onClose: () => void
}) {
  return (
    <div className="common-detail-panel">
      <div className="common-detail-header">
        <div>
          <div className="eyebrow">COMMON MATERIAL</div>
          <h2>{material.nmc}</h2>
          <p>{material.description}</p>
        </div>

        <button className="common-close-button" onClick={onClose}>
          ×
        </button>
      </div>

      <div className="common-detail-section">
        <div className="common-detail-title-row">
          <h3>Canonical Record</h3>
          <ApprovalBadge status={material.status} />
        </div>

        <div className="common-spec-grid">
          <div>
            <span>Common National Material Code</span>
            <strong>{material.nmc}</strong>
          </div>

          <div>
            <span>Category</span>
            <strong>{material.category}</strong>
          </div>

          <div>
            <span>Material / Grade</span>
            <strong>{material.material}</strong>
          </div>

          <div>
            <span>Size / Dimension</span>
            <strong>{material.size}</strong>
          </div>

          <div>
            <span>Pressure / Rating</span>
            <strong>{material.pressure}</strong>
          </div>

          <div>
            <span>Source Records</span>
            <strong>{material.sourceCount} CPSE records</strong>
          </div>
        </div>
      </div>

      <div className="common-detail-section">
        <h3>CPSE Source Mappings</h3>

        <div className="common-source-list">
          {material.sources.map((source) => (
            <div
              className="common-source-item"
              key={`${source.cpse}-${source.code}`}
            >
              <div className="common-source-top">
                <strong>{source.cpse}</strong>
                <span>{source.code}</span>
              </div>

              <p>{source.description}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="common-detail-section">
        <h3>Governance</h3>

        <div className="common-governance-row">
          <span>Approval status</span>
          <ApprovalBadge status={material.status} />
        </div>

        <div className="common-governance-row">
          <span>Canonical values</span>
          <strong>
            {material.status === 'APPROVED'
              ? 'No critical fields unresolved'
              : 'Requires human validation'}
          </strong>
        </div>

        <div className="common-governance-row">
          <span>Source mapping</span>
          <strong>{material.sourceCount} linked records</strong>
        </div>
      </div>
    </div>
  )
}

export default function CommonMaterials() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All Categories')
  const [status, setStatus] = useState('All Statuses')
  const [selected, setSelected] = useState<CommonMaterial | null>(null)

  const filteredMaterials = useMemo(() => {
    const query = search.trim().toLowerCase()

    return commonMaterials.filter((material) => {
      const matchesSearch =
        !query ||
        material.nmc.toLowerCase().includes(query) ||
        material.description.toLowerCase().includes(query) ||
        material.material.toLowerCase().includes(query) ||
        material.sources.some(
          (source) =>
            source.code.toLowerCase().includes(query) ||
            source.cpse.toLowerCase().includes(query),
        )

      const matchesCategory =
        category === 'All Categories' ||
        material.category === category

      const matchesStatus =
        status === 'All Statuses' ||
        material.status === status

      return matchesSearch && matchesCategory && matchesStatus
    })
  }, [search, category, status])

  const approvedCount = commonMaterials.filter(
    (material) => material.status === 'APPROVED',
  ).length

  const sourceLinks = commonMaterials.reduce(
    (total, material) => total + material.sourceCount,
    0,
  )

  return (
    <div className="page">
      <div className="page-header common-page-header">
        <div>
          <div className="eyebrow">HARMONIZED MATERIAL MASTER</div>
          <h1>Common Materials</h1>
          <p>
            Review standardized material records and their CPSE source mappings.
          </p>
        </div>

        <div className="common-header-status">
          <span className="common-header-dot" />
          Common master active
        </div>
      </div>

      <div className="common-summary">
        <div>
          <span>Common Materials</span>
          <strong>{commonMaterials.length}</strong>
        </div>

        <div>
          <span>Approved</span>
          <strong>{approvedCount}</strong>
        </div>

        <div>
          <span>CPSE Source Links</span>
          <strong>{sourceLinks}</strong>
        </div>

        <div>
          <span>Pending Governance</span>
          <strong>
            {commonMaterials.filter(
              (material) => material.status === 'REVIEW',
            ).length}
          </strong>
        </div>
      </div>

      <div className="common-info-banner">
        <div className="common-info-icon">i</div>

        <div>
          <strong>Common records preserve source identity</strong>
          <p>
            Each Common National Material Code remains linked to the original
            CPSE material codes. Source records are not replaced.
          </p>
        </div>
      </div>

      <div className="common-card">
        <div className="common-toolbar">
          <input
            className="common-search"
            type="text"
            placeholder="Search NMC, description, material code or CPSE..."
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

        <div className="common-table-wrapper">
          <table className="common-table">
            <thead>
              <tr>
                <th>Common National Code</th>
                <th>Standardized Description</th>
                <th>Category</th>
                <th>Material / Grade</th>
                <th>Specification</th>
                <th>CPSE Sources</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {filteredMaterials.map((material) => (
                <tr
                  key={material.nmc}
                  onClick={() => setSelected(material)}
                >
                  <td>
                    <span className="nmc-code">{material.nmc}</span>
                  </td>

                  <td className="common-description">
                    {material.description}
                  </td>

                  <td>{material.category}</td>

                  <td>{material.material}</td>

                  <td>
                    <div className="common-spec-cell">
                      <span>{material.size}</span>
                      {material.pressure !== '—' && (
                        <small>{material.pressure}</small>
                      )}
                    </div>
                  </td>

                  <td>
                    <div className="source-count">
                      <strong>{material.sourceCount}</strong>
                      <span>CPSEs</span>
                    </div>
                  </td>

                  <td>
                    <ApprovalBadge status={material.status} />
                  </td>
                </tr>
              ))}

              {filteredMaterials.length === 0 && (
                <tr>
                  <td colSpan={7} className="common-empty">
                    No common materials match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="common-footer">
          Showing {filteredMaterials.length} of {commonMaterials.length} demo
          common materials
        </div>
      </div>

      {selected && (
        <div
          className="common-detail-overlay"
          onClick={() => setSelected(null)}
        >
          <div
            className="common-detail-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <CommonMaterialDetails
              material={selected}
              onClose={() => setSelected(null)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
