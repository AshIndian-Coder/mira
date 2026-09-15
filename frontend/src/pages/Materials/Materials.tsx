import { useCallback, useEffect, useState, type ChangeEvent } from 'react'

import Button from '../../components/UI/Button'
import { api, formatNumber, type Material } from '../../lib/api'

function Materials() {
  const [materials, setMaterials] = useState<Material[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [matching, setMatching] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadMaterials = useCallback(async (search = query) => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.listMaterials({
        query: search || undefined,
        limit: 100,
      })
      setMaterials(response.materials)
      setTotal(response.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load materials')
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => {
    let active = true
    api.listMaterials({
      query: query || undefined,
      limit: 100,
    }).then((response) => {
      if (active) {
        setMaterials(response.materials)
        setTotal(response.total)
        setLoading(false)
      }
    }).catch((err) => {
      if (active) {
        setError(err instanceof Error ? err.message : 'Failed to load materials')
        setLoading(false)
      }
    })
    return () => {
      active = false
    }
  }, [query])

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setUploading(true)
      setError(null)
      const result = await api.uploadMaterials(file)
      setMessage(
        `Uploaded ${result.records_ingested} records (${formatNumber(result.total_materials)} total)`,
      )
      await loadMaterials()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  const handleRunMatching = async () => {
    try {
      setMatching(true)
      setError(null)
      const result = await api.runBatchMatching(false)
      setMessage(
        `Matching complete: ${result.new_candidates_stored} new candidates in ${result.elapsed_ms}ms`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Matching failed')
    } finally {
      setMatching(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <span className="eyebrow">MATERIAL MASTER</span>
          <h1>Materials</h1>
          <p>Upload CPSE CSV files and browse ingested material records.</p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <label className="materials-upload-button">
            {uploading ? 'Uploading…' : 'Upload CSV'}
            <input
              type="file"
              accept=".csv"
              hidden
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
          <Button onClick={handleRunMatching} disabled={matching || total === 0}>
            {matching ? 'Running…' : 'Run Matching'}
          </Button>
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
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') loadMaterials(query)
            }}
          />
          <button
            className="mapping-secondary-button"
            type="button"
            onClick={() => loadMaterials(query)}
          >
            Search
          </button>
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
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="mapping-empty">
                    Loading materials…
                  </td>
                </tr>
              ) : materials.length === 0 ? (
                <tr>
                  <td colSpan={5} className="mapping-empty">
                    No materials yet. Upload a CSV to get started.
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
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="mapping-footer">
          Showing {materials.length} of {formatNumber(total)} materials
        </div>
      </div>
    </div>
  )
}

export default Materials
