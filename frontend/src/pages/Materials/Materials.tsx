import { useCallback, useEffect, useState, type ChangeEvent } from 'react'

import Button from '../../components/UI/Button'
import CnmcMatchModal from '../../components/Matching/CnmcMatchModal'
import { useAuth } from '../../context/AuthContext'
import { useOperation } from '../../context/OperationContext'
import { activeJobs, api, formatNumber, type JobProgress, type Material } from '../../lib/api'

const PAGE_SIZE = 50

function Materials() {
  const { isDataSteward } = useAuth()
  const [materials, setMaterials] = useState<Material[]>([])
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const [limit] = useState(PAGE_SIZE)
  const [query, setQuery] = useState('')
  const [selectedCpse, setSelectedCpse] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [cpses, setCpses] = useState<string[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const { isActive, begin, end } = useOperation()
  const uploading = isActive('upload')
  const matching = isActive('matching')
  const cnmcMatching = isActive('cnmcMatching')
  const [selectedMaterialForCnmc, setSelectedMaterialForCnmc] = useState<Material | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<JobProgress | null>(null)

  useEffect(() => {
    if (!matching) { setProgress(null); return }
    let alive = true
    const tick = async () => {
      const jobs = await activeJobs('matching').catch(() => [])
      if (alive) setProgress(jobs[0] ?? null)
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => { alive = false; clearInterval(t) }
  }, [matching])

  const loadStats = useCallback(async () => {
    try {
      const stats = await api.materialsStats()
      setCpses(stats.cpse_list || [])
      const cats = Object.keys(stats.category_distribution || {})
        .filter(Boolean)
        .sort()
      setCategories(cats)
    } catch {
      // Non-blocking fallback
    }
  }, [])

  useEffect(() => {
    let active = true
    api.materialsStats()
      .then((stats) => {
        if (active) {
          setCpses(stats.cpse_list || [])
          const cats = Object.keys(stats.category_distribution || {})
            .filter(Boolean)
            .sort()
          setCategories(cats)
        }
      })
      .catch(() => {
        // Non-blocking fallback
      })
    return () => {
      active = false
    }
  }, [])

  const loadMaterials = useCallback(
    async (
      search = query,
      cpse = selectedCpse,
      category = selectedCategory,
      offset = skip,
    ) => {
      try {
        setLoading(true)
        setError(null)
        const response = await api.listMaterials({
          query: search.trim() || undefined,
          cpse: cpse || undefined,
          category: category || undefined,
          skip: offset,
          limit,
        })
        setMaterials(response.materials)
        setTotal(response.total)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load materials')
      } finally {
        setLoading(false)
      }
    },
    [query, selectedCpse, selectedCategory, skip, limit],
  )

  useEffect(() => {
    let active = true
    api
      .listMaterials({
        query: query.trim() || undefined,
        cpse: selectedCpse || undefined,
        category: selectedCategory || undefined,
        skip,
        limit,
      })
      .then((response) => {
        if (active) {
          setMaterials(response.materials)
          setTotal(response.total)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load materials')
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [query, selectedCpse, selectedCategory, skip, limit])

  const handleSearchChange = (event: ChangeEvent<HTMLInputElement>) => {
    setQuery(event.target.value)
    setSkip(0)
  }

  const handleCpseChange = (newCpse: string) => {
    setSelectedCpse(newCpse)
    setSkip(0)
  }

  const handleCategoryChange = (newCat: string) => {
    setSelectedCategory(newCat)
    setSkip(0)
  }

  const handleResetFilters = () => {
    setQuery('')
    setSelectedCpse('')
    setSelectedCategory('')
    setSkip(0)
  }

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      begin('upload')
      setError(null)
      const result = await api.uploadMaterials(file)
      setMessage(
        `Uploaded ${result.records_ingested} records (${formatNumber(result.total_materials)} total)`,
      )
      setSkip(0)
      await Promise.all([loadStats(), loadMaterials(query, selectedCpse, selectedCategory, 0)])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      end('upload')
      event.target.value = ''
    }
  }

  const handleRunMatching = async () => {
    try {
      begin('matching')
      setError(null)
      const result = await api.runBatchMatching(false)
      setMessage(
        `Pairwise matching complete: ${result.new_candidates_stored} new candidates in ${result.elapsed_ms}ms`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Matching failed')
    } finally {
      end('matching')
    }
  }

  const handleRunCnmcMatching = async () => {
    try {
      begin('cnmcMatching')
      setError(null)
      const result = await api.runCnmcBatchMatching(5, 0.65)
      if (result.status === 'no_existing_cnmc') {
        setMessage('No registered CNMCs found in catalog. Run standard pairwise matching and mapping generation first.')
      } else {
        setMessage(
          `CNMC matching complete: ${result.proposals_generated} candidate proposals generated across ${result.materials_evaluated} materials. Review them in Match Review.`,
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'CNMC matching failed')
    } finally {
      end('cnmcMatching')
    }
  }

  const start = total === 0 ? 0 : skip + 1
  const endCount = Math.min(skip + limit, total)
  const isFirstPage = skip === 0
  const isLastPage = skip + limit >= total || materials.length === 0
  const currentPage = Math.floor(skip / limit) + 1
  const totalPages = Math.ceil(total / limit) || 1
  const hasActiveFilters = Boolean(query || selectedCpse || selectedCategory)

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <span className="eyebrow">MATERIAL MASTER</span>
          <h1>Materials</h1>
          <p>Upload CPSE CSV files and browse ingested material records.</p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {isDataSteward && (
            <>
              <label
                className="materials-upload-button"
                title="Reads a CSV, Excel, XML, JSON or text catalogue, stores every row and computes its embedding vector."
              >
                {uploading ? 'Uploading…' : 'Upload File'}
                <input
                  type="file"
                  accept=".csv,.txt,.xml,.json,.xls,.xlsx"
                  hidden
                  onChange={handleUpload}
                  disabled={uploading}
                />
              </label>
              <Button
                onClick={handleRunMatching}
                disabled={matching || cnmcMatching || total === 0}
                title="Scores every cross-CPSE material pair on five components and files the results in the review queue. Runs on the server and can take several minutes."
              >
                {matching ? 'Running…' : 'Run Matching'}
              </Button>
              <Button
                onClick={handleRunCnmcMatching}
                disabled={cnmcMatching || matching || total === 0}
                title="Checks each material against national codes that already exist, so a new item can attach to an existing code instead of creating one."
              >
                {cnmcMatching ? 'Matching CNMCs…' : 'Match to CNMCs'}
              </Button>
            </>
          )}

          {progress && progress.total > 0 && (
            <div style={{ width: '100%', marginTop: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                <span>{progress.detail}</span>
                <span>{Math.round((progress.processed / progress.total) * 100)}%</span>
              </div>
              <div style={{ height: 6, background: 'rgba(0,0,0,0.08)', borderRadius: 3, marginTop: 4 }}>
                <div
                  style={{
                    height: '100%',
                    width: `${(progress.processed / progress.total) * 100}%`,
                    background: 'var(--accent, #2563eb)',
                    borderRadius: 3,
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {message && (
        <div className="common-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="common-info-icon">✓</div>
          <div>
            <strong>Success</strong>
            <p>{message}</p>
          </div>
        </div>
      )}

      {error && (
        <div className="mapping-info-banner" style={{ marginBottom: '1rem' }}>
          <div className="mapping-info-icon">!</div>
          <div>
            <strong>Error</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <div className="mapping-card">
        <div className="mapping-toolbar">
          <input
            className="mapping-search"
            type="text"
            placeholder="Search description or material code…"
            value={query}
            onChange={handleSearchChange}
            onKeyDown={(event) => {
              if (event.key === 'Enter') loadMaterials()
            }}
          />
          <select
            className="mapping-select"
            value={selectedCpse}
            onChange={(event) => handleCpseChange(event.target.value)}
            aria-label="Filter by CPSE"
          >
            <option value="">All CPSEs</option>
            {cpses.map((cpse) => (
              <option key={cpse} value={cpse}>
                {cpse}
              </option>
            ))}
          </select>
          <select
            className="mapping-select"
            value={selectedCategory}
            onChange={(event) => handleCategoryChange(event.target.value)}
            aria-label="Filter by Category"
          >
            <option value="">All Categories</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
          <button
            className="mapping-secondary-button"
            type="button"
            onClick={() => loadMaterials()}
            title="Reload the material list from the database."
          >
            Search
          </button>
          {hasActiveFilters && (
            <button
              className="mapping-secondary-button"
              type="button"
              onClick={handleResetFilters}
              title="Clear the search box and the CPSE and category filters."
            >
              Reset
            </button>
          )}
        </div>

        <div className="mapping-table-wrapper">
          <table className="mapping-table">
            <thead>
              <tr>
                <th>CPSE</th>
                <th>Material Code</th>
                <th>Description</th>
                <th>Category</th>
                <th>Grade</th>
                <th style={{ width: '130px', textAlign: 'right' }}>CNMC</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="mapping-empty">
                    Loading materials…
                  </td>
                </tr>
              ) : materials.length === 0 ? (
                <tr>
                  <td colSpan={6} className="mapping-empty">
                    {hasActiveFilters
                      ? 'No materials match the selected filter criteria.'
                      : 'No materials yet. Upload a CSV to get started.'}
                  </td>
                </tr>
              ) : (
                materials.map((material) => (
                  <tr key={material.id}>
                    <td>
                      <strong className="mapping-cpse">{material.cpse}</strong>
                    </td>
                    <td>
                      <span className="mapping-code">{material.material_code}</span>
                    </td>
                    <td className="mapping-description">{material.description}</td>
                    <td>{material.category}</td>
                    <td>{material.material_grade ?? '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="mapping-secondary-button"
                        type="button"
                        style={{
                          height: '28px',
                          padding: '0 10px',
                          fontSize: '11px',
                          fontWeight: 600,
                        }}
                        onClick={() => setSelectedMaterialForCnmc(material)}
                        title="Open the full record for this material, including its parsed specifications."
                      >
                        Find CNMC
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="mapping-footer">
          <span>
            Showing {total === 0 ? 0 : `${formatNumber(start)}–${formatNumber(endCount)}`} of {formatNumber(total)} materials
          </span>
          <div className="mapping-pagination">
            <button
              className="mapping-pagination-btn"
              type="button"
              disabled={isFirstPage || loading}
              onClick={() => setSkip((prev) => Math.max(0, prev - limit))}
              title="Show the previous 50 materials."
            >
              Previous
            </button>
            <span className="mapping-page-indicator">
              Page {formatNumber(currentPage)} of {formatNumber(totalPages)}
            </span>
            <button
              className="mapping-pagination-btn"
              type="button"
              disabled={isLastPage || loading}
              onClick={() => setSkip((prev) => prev + limit)}
              title="Show the next 50 materials."
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {selectedMaterialForCnmc && (
        <CnmcMatchModal
          material={selectedMaterialForCnmc}
          onClose={() => setSelectedMaterialForCnmc(null)}
          onAttached={() => loadMaterials()}
        />
      )}
    </div>
  )
}

export default Materials
