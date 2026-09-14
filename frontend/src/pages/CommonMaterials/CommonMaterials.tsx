import { useEffect, useMemo, useState } from 'react'

import { api, type Mapping } from '../../lib/api'

type CommonMaterial = {
  nmc: string
  description: string
  category: string
  material: string
  status: string
  sourceCount: number
  sources: Array<{ cpse: string; code: string; description: string }>
}

function ApprovalBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase()
  const label =
    normalized === 'PROVISIONAL'
      ? 'Provisional'
      : normalized === 'APPROVED'
        ? 'Approved'
        : status

  const className =
    normalized === 'APPROVED'
      ? 'approved'
      : normalized === 'PROVISIONAL'
        ? 'provisional'
        : 'review'

  return (
    <span className={`common-status common-status-${className}`}>
      {label}
    </span>
  )
}

function mappingToCommonMaterial(mapping: Mapping): CommonMaterial {
  const primary = mapping.cpse_mappings[0]
  return {
    nmc: mapping.nmc,
    description: primary?.description ?? mapping.nmc,
    category: primary?.category ?? 'General',
    material: primary?.material_grade ?? '—',
    status: mapping.status,
    sourceCount: mapping.cpse_mappings.length,
    sources: mapping.cpse_mappings.map((entry) => ({
      cpse: entry.cpse,
      code: entry.material_code,
      description: entry.description,
    })),
  }
}

export default function CommonMaterials() {
  const [materials, setMaterials] = useState<CommonMaterial[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<CommonMaterial | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const response = await api.listMappings()
        setMaterials(response.mappings.map(mappingToCommonMaterial))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load common materials')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const filteredMaterials = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return materials
    return materials.filter(
      (material) =>
        material.nmc.toLowerCase().includes(query) ||
        material.description.toLowerCase().includes(query) ||
        material.sources.some(
          (source) =>
            source.code.toLowerCase().includes(query) ||
            source.cpse.toLowerCase().includes(query),
        ),
    )
  }, [materials, search])

  const sourceLinks = materials.reduce((total, material) => total + material.sourceCount, 0)

  return (
    <div className="page">
      <div className="page-header common-page-header">
        <div>
          <div className="eyebrow">HARMONIZED MATERIAL MASTER</div>
          <h1>Common Materials</h1>
          <p>Review standardized material records and their CPSE source mappings.</p>
        </div>
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

      <div className="common-summary">
        <div>
          <span>Common Materials</span>
          <strong>{loading ? '—' : materials.length}</strong>
        </div>
        <div>
          <span>CPSE Source Links</span>
          <strong>{loading ? '—' : sourceLinks}</strong>
        </div>
      </div>

      <div className="common-card">
        <div className="common-toolbar">
          <input
            className="common-search"
            type="text"
            placeholder="Search NMC, description, material code or CPSE…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <div className="common-table-wrapper">
          <table className="common-table">
            <thead>
              <tr>
                <th>Common National Code</th>
                <th>Representative Description</th>
                <th>Category</th>
                <th>Material / Grade</th>
                <th>CPSE Sources</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="common-empty">
                    Loading common materials…
                  </td>
                </tr>
              ) : filteredMaterials.length === 0 ? (
                <tr>
                  <td colSpan={6} className="common-empty">
                    No common materials yet. Generate mappings after approving matches.
                  </td>
                </tr>
              ) : (
                filteredMaterials.map((material) => (
                  <tr key={material.nmc} onClick={() => setSelected(material)}>
                    <td>
                      <span className="nmc-code">{material.nmc}</span>
                    </td>
                    <td className="common-description">{material.description}</td>
                    <td>{material.category}</td>
                    <td>{material.material}</td>
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
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="common-detail-overlay" onClick={() => setSelected(null)}>
          <div className="common-detail-modal" onClick={(event) => event.stopPropagation()}>
            <div className="common-detail-panel">
              <div className="common-detail-header">
                <div>
                  <div className="eyebrow">COMMON MATERIAL</div>
                  <h2>{selected.nmc}</h2>
                  <p>{selected.description}</p>
                </div>
                <button className="common-close-button" onClick={() => setSelected(null)}>
                  ×
                </button>
              </div>
              <div className="common-detail-section">
                <h3>CPSE Source Mappings</h3>
                <div className="common-source-list">
                  {selected.sources.map((source) => (
                    <div className="common-source-item" key={`${source.cpse}-${source.code}`}>
                      <div className="common-source-top">
                        <strong>{source.cpse}</strong>
                        <span>{source.code}</span>
                      </div>
                      <p>{source.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
