import { useEffect, useMemo, useState } from 'react'

import { api, type CommonMaterialRecord, type Mapping } from '../../lib/api'

type CommonMaterial = {
  nmc: string
  description: string
  category: string
  material: string
  status: string
  sourceCount: number
  technicalAttributes: Record<string, unknown>
  unknownFields: string[]
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

function formatAttributeLabel(field: string): string {
  return field
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function formatAttributeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'UNKNOWN'

  if (Array.isArray(value)) {
    return value.length ? value.join(', ') : 'UNKNOWN'
  }

  if (typeof value === 'object' && value !== null) {
    const obj = value as Record<string, any>
    if ('value' in obj && 'unit' in obj) {
      return `${obj.value} ${obj.unit}`
    }
    if ('diameter' in obj && 'length' in obj) {
      const dia = typeof obj.diameter === 'object' && obj.diameter !== null ? obj.diameter.value : obj.diameter
      const len = typeof obj.length === 'object' && obj.length !== null ? obj.length.value : obj.length
      const unit = (typeof obj.length === 'object' && obj.length?.unit) || (typeof obj.diameter === 'object' && obj.diameter?.unit) || 'MM'
      if ('pitch' in obj) {
        const pitch = typeof obj.pitch === 'object' && obj.pitch !== null ? obj.pitch.value : obj.pitch
        return `M${dia} × ${pitch} × ${len} ${unit}`
      }
      return `M${dia} × ${len} ${unit}`
    }
    if ('nominal_diameter' in obj && 'pitch' in obj) {
      return `M${obj.nominal_diameter} × ${obj.pitch} ${obj.unit || 'MM'}`
    }
    return JSON.stringify(value)
  }

  return String(value)
}

function mappingToCommonMaterial(mapping: Mapping): CommonMaterial {
  const cmr: CommonMaterialRecord = mapping.common_material_record
  const technicalAttributes = cmr.canonical_technical_attributes ?? {}

  return {
    nmc: mapping.cnmc || mapping.nmc || '—',
    description: cmr.canonical_description,
    category: cmr.category,
    material: formatAttributeValue(technicalAttributes.material_grade),
    status: cmr.approval_status,
    sourceCount: cmr.provenance.source_count,
    technicalAttributes,
    unknownFields: cmr.critical_unknown_fields,
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
        (material.nmc || '').toLowerCase().includes(query) ||
        (material.description || '').toLowerCase().includes(query) ||
        material.sources.some(
          (source) =>
            (source.code || '').toLowerCase().includes(query) ||
            (source.cpse || '').toLowerCase().includes(query),
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
            placeholder="Search CNMC, description, material code or CPSE…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <div className="common-table-wrapper">
          <table className="common-table">
            <thead>
              <tr>
                <th>Common National Code (CNMC)</th>
                <th>Canonical Description</th>
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
            <div className="common-detail-header">
              <div>
                <div className="eyebrow">COMMON MATERIAL</div>
                <h2>{selected.nmc}</h2>
                <p>{selected.description}</p>
              </div>
              <button
                type="button"
                className="common-close-button"
                onClick={() => setSelected(null)}
                title="Close this record."
              >
                ×
              </button>
            </div>

            <div className="common-detail-body">
              <div className="common-detail-section">
                <h3>Canonical Technical Attributes</h3>
                <div className="common-source-list">
                  {Object.entries(selected.technicalAttributes).map(([field, value]) => (
                    <div className="common-source-item" key={field}>
                      <div className="common-source-top">
                        <strong>{formatAttributeLabel(field)}</strong>
                        <span>{formatAttributeValue(value)}</span>
                      </div>
                    </div>
                  ))}
                </div>
                {selected.unknownFields.length > 0 && (
                  <p style={{ marginTop: '10px', color: 'var(--text-muted)', fontSize: '11.5px' }}>
                    {selected.unknownFields.length} field(s) remain UNKNOWN because source
                    evidence is missing or conflicting.
                  </p>
                )}
              </div>

              <div className="common-detail-section" style={{ marginTop: '24px' }}>
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