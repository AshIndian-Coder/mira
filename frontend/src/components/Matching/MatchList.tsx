import { useMemo, useState, useEffect } from 'react'
import type { Candidate } from '../../lib/api'
import { formatPercent } from '../../lib/api'
import Badge from '../UI/Badge'

type MatchListProps = {
  candidates: Candidate[]
  selectedId: number | null
  onSelect: (candidate: Candidate) => void
  loading?: boolean
  skip?: number
  limit?: number
  totalPending?: number
  onPrevPage?: () => void
  onNextPage?: () => void
}

type FilterType = 'ALL' | 'CONFLICT' | 'REVIEW' | 'HIGH_CONFIDENCE'

const formatNumber = (val: number) => val.toLocaleString()

function MatchList({
  candidates,
  selectedId,
  onSelect,
  loading = false,
  skip = 0,
  limit = 50,
  totalPending,
  onPrevPage,
  onNextPage,
}: MatchListProps) {
  const [filterType, setFilterType] = useState<FilterType>('ALL')
  const [searchQuery, setSearchQuery] = useState('')
  const [cpseFilter, setCpseFilter] = useState<string>('ALL')

  // Calculate distinct CPSEs from loaded candidates
  const availableCpses = useMemo(() => {
    const cpses = new Set<string>()
    candidates.forEach((c) => {
      if (c.source_cpse) cpses.add(c.source_cpse)
      if (c.target_cpse) cpses.add(c.target_cpse)
    })
    return Array.from(cpses).sort()
  }, [candidates])

  // Count by actual queue categories
  const counts = useMemo(() => {
    return {
      ALL: candidates.length,
      CONFLICT: candidates.filter((c) =>
        c.critical_checks?.some((chk) => chk.status === 'CONFLICT'),
      ).length,
      REVIEW: candidates.filter((c) => c.engine_decision === 'REVIEW').length,
      HIGH_CONFIDENCE: candidates.filter(
        (c) => c.engine_decision === 'HIGH_CONFIDENCE',
      ).length,
    }
  }, [candidates])

  // Filter candidates
  const filteredCandidates = useMemo(() => {
    return candidates.filter((c) => {
      // 1. Category / Status filter
      if (filterType === 'CONFLICT') {
        const hasConflict = c.critical_checks?.some((chk) => chk.status === 'CONFLICT')
        if (!hasConflict) return false
      } else if (filterType === 'REVIEW') {
        if (c.engine_decision !== 'REVIEW') return false
      } else if (filterType === 'HIGH_CONFIDENCE') {
        if (c.engine_decision !== 'HIGH_CONFIDENCE') return false
      }

      // 2. CPSE filter
      if (
        cpseFilter !== 'ALL' &&
        c.source_cpse !== cpseFilter &&
        c.target_cpse !== cpseFilter
      ) {
        return false
      }

      // 3. Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim()
        const text = `${c.source_code} ${c.target_code} ${c.source_description} ${c.target_description} ${c.source_cpse} ${c.target_cpse}`.toLowerCase()
        if (!text.includes(q)) {
          return false
        }
      }

      return true
    })
  }, [candidates, filterType, cpseFilter, searchQuery])

  // Auto-select first item if current selection is filtered out
  useEffect(() => {
    if (filteredCandidates.length > 0) {
      const isSelectedInFilter = filteredCandidates.some((c) => c.id === selectedId)
      if (!isSelectedInFilter) {
        onSelect(filteredCandidates[0])
      }
    }
  }, [filteredCandidates, selectedId, onSelect])

  const clearFilters = () => {
    setFilterType('ALL')
    setSearchQuery('')
    setCpseFilter('ALL')
  }

  const isFiltered = filterType !== 'ALL' || searchQuery.trim() !== '' || cpseFilter !== 'ALL'

  const effectiveTotal = totalPending ?? candidates.length
  const currentPage = Math.floor(skip / limit) + 1
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / limit))
  const isFirstPage = skip <= 0
  const isLastPage = skip + limit >= effectiveTotal
  const start = effectiveTotal === 0 ? 0 : skip + 1
  const end = Math.min(skip + candidates.length, effectiveTotal)

  return (
    <div className="section-card match-list" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div className="section-header" style={{ marginBottom: '4px' }}>
        <div>
          <h2>Candidate Matches</h2>
          <p>
            {filteredCandidates.length} of {candidates.length} on page
            {totalPending !== undefined && totalPending !== candidates.length ? ` (${formatNumber(totalPending)} total pending)` : ''}
          </p>
        </div>
      </div>

      {/* Filter Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* Search Input */}
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            placeholder="Search code, desc, CPSE…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '7px 10px',
              fontSize: '12px',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              style={{
                position: 'absolute',
                right: '8px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                fontSize: '14px',
                cursor: 'pointer',
                color: 'var(--text-muted)',
              }}
            >
              ×
            </button>
          )}
        </div>

        {/* Filter Pills */}
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          <button
            type="button"
            className={`filter-pill ${filterType === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilterType('ALL')}
            style={{
              padding: '4px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              fontWeight: 650,
              border: '1px solid',
              borderColor: filterType === 'ALL' ? 'var(--primary)' : 'var(--border-default)',
              background: filterType === 'ALL' ? 'var(--primary)' : 'var(--bg-surface-subtle)',
              color: filterType === 'ALL' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 120ms ease',
            }}
          >
            All ({counts.ALL})
          </button>

          {counts.CONFLICT > 0 && (
            <button
              type="button"
              className={`filter-pill ${filterType === 'CONFLICT' ? 'active' : ''}`}
              onClick={() => setFilterType('CONFLICT')}
              style={{
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '11px',
                fontWeight: 650,
                border: '1px solid',
                borderColor: filterType === 'CONFLICT' ? '#ef4444' : 'var(--border-default)',
                background: filterType === 'CONFLICT' ? '#fef2f2' : 'var(--bg-surface-subtle)',
                color: filterType === 'CONFLICT' ? '#991b1b' : '#ef4444',
                cursor: 'pointer',
                transition: 'all 120ms ease',
              }}
            >
              ⚠️ Conflicts ({counts.CONFLICT})
            </button>
          )}

          <button
            type="button"
            className={`filter-pill ${filterType === 'REVIEW' ? 'active' : ''}`}
            onClick={() => setFilterType('REVIEW')}
            style={{
              padding: '4px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              fontWeight: 650,
              border: '1px solid',
              borderColor: filterType === 'REVIEW' ? '#f59e0b' : 'var(--border-default)',
              background: filterType === 'REVIEW' ? '#fffbeb' : 'var(--bg-surface-subtle)',
              color: filterType === 'REVIEW' ? '#92400e' : 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 120ms ease',
            }}
          >
            Needs Review ({counts.REVIEW})
          </button>

          {counts.HIGH_CONFIDENCE > 0 && (
            <button
              type="button"
              className={`filter-pill ${filterType === 'HIGH_CONFIDENCE' ? 'active' : ''}`}
              onClick={() => setFilterType('HIGH_CONFIDENCE')}
              style={{
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '11px',
                fontWeight: 650,
                border: '1px solid',
                borderColor: filterType === 'HIGH_CONFIDENCE' ? '#10b981' : 'var(--border-default)',
                background: filterType === 'HIGH_CONFIDENCE' ? '#ecfdf5' : 'var(--bg-surface-subtle)',
                color: filterType === 'HIGH_CONFIDENCE' ? '#065f46' : 'var(--text-secondary)',
                cursor: 'pointer',
                transition: 'all 120ms ease',
              }}
            >
              High Conf ({counts.HIGH_CONFIDENCE})
            </button>
          )}
        </div>

        {/* CPSE Dropdown (if multiple CPSEs exist) */}
        {availableCpses.length > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>
              CPSE:
            </label>
            <select
              value={cpseFilter}
              onChange={(e) => setCpseFilter(e.target.value)}
              style={{
                flex: 1,
                padding: '4px 8px',
                fontSize: '11px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-default)',
                background: 'var(--bg-surface)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="ALL">All CPSEs</option>
              {availableCpses.map((cpse) => (
                <option key={cpse} value={cpse}>
                  {cpse}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Candidate List Body */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', maxHeight: 'calc(100vh - 330px)' }}>
        {loading ? (
          <div className="match-item">
            <span>Loading review queue…</span>
          </div>
        ) : filteredCandidates.length === 0 ? (
          <div
            style={{
              padding: '24px 16px',
              textAlign: 'center',
              background: 'var(--bg-surface-subtle)',
              borderRadius: 'var(--radius-md)',
              border: '1px dashed var(--border-default)',
            }}
          >
            <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-muted)' }}>
              {isFiltered ? 'No candidates match the selected filters.' : 'No pending reviews in queue.'}
            </p>
            {isFiltered && (
              <button
                type="button"
                onClick={clearFilters}
                style={{
                  marginTop: '8px',
                  background: 'none',
                  border: 'none',
                  color: 'var(--accent-brand)',
                  fontSize: '11.5px',
                  fontWeight: 650,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Clear all filters
              </button>
            )}
          </div>
        ) : (
          filteredCandidates.map((candidate) => {
            const isSelected = selectedId === candidate.id
            const hasConflict = candidate.critical_checks?.some((c) => c.status === 'CONFLICT')
            const scorePercent = formatPercent(candidate.scores?.final_score ?? 0, 0)

            return (
              <button
                type="button"
                key={candidate.id}
                className={`match-item ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelect(candidate)}
                style={{
                  width: '100%',
                  border: isSelected ? '1px solid #0f172a' : '1px solid var(--border-subtle)',
                  background: isSelected ? '#ffffff' : 'var(--bg-surface-subtle)',
                  textAlign: 'left',
                  cursor: 'pointer',
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  transition: 'all 120ms ease',
                  boxShadow: isSelected ? 'var(--shadow-sm)' : 'none',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      color: isSelected ? 'var(--primary)' : 'var(--text-primary)',
                    }}
                  >
                    {candidate.source_cpse} · {candidate.source_code}
                  </span>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {hasConflict && (
                      <span
                        title="Critical specification conflict"
                        style={{
                          fontSize: '10px',
                          color: '#ef4444',
                          fontWeight: 800,
                          background: '#fef2f2',
                          padding: '1px 4px',
                          borderRadius: '3px',
                          border: '1px solid #fecaca',
                        }}
                      >
                        ⚠️ CONFLICT
                      </span>
                    )}

                    <b
                      style={{
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)',
                        background: isSelected ? '#0f172a' : '#e2e8f0',
                        color: isSelected ? '#ffffff' : '#0f172a',
                        fontSize: '11px',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 750,
                      }}
                    >
                      {scorePercent}
                    </b>
                  </div>
                </div>

                <span
                  style={{
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: '300px',
                    lineHeight: 1.3,
                  }}
                >
                  {candidate.source_description}
                </span>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', marginTop: '2px' }}>
                  <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                    vs {candidate.target_cpse} · {candidate.target_code}
                  </span>
                  <Badge
                    variant={
                      candidate.engine_decision === 'HIGH_CONFIDENCE'
                        ? 'success'
                        : candidate.engine_decision === 'DIFFERENT'
                          ? 'neutral'
                          : 'review'
                    }
                  >
                    {candidate.engine_decision === 'HIGH_CONFIDENCE' ? 'High Conf' : candidate.engine_decision}
                  </Badge>
                </div>
              </button>
            )
          })
        )}
      </div>

      {/* Pagination Footer */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          paddingTop: '10px',
          borderTop: '1px solid var(--border-subtle)',
          fontSize: '11.5px',
          color: 'var(--text-muted)',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        <span>
          {effectiveTotal === 0
            ? '0 items'
            : `Showing ${formatNumber(start)}–${formatNumber(end)} of ${formatNumber(effectiveTotal)}`}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            type="button"
            className="mapping-pagination-btn"
            disabled={isFirstPage || loading}
            onClick={onPrevPage}
            style={{ padding: '0 8px', height: '26px', fontSize: '11px' }}
          >
            Previous
          </button>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Page {formatNumber(currentPage)} of {formatNumber(totalPages)}
          </span>
          <button
            type="button"
            className="mapping-pagination-btn"
            disabled={isLastPage || loading}
            onClick={onNextPage}
            style={{ padding: '0 8px', height: '26px', fontSize: '11px' }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}

export default MatchList
