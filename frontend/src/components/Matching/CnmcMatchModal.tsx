import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { api, formatPercent, type Material, type MatchScores, type CriticalCheck } from '../../lib/api'
import Badge from '../UI/Badge'
import Button from '../UI/Button'
import CriticalChecks from './CriticalChecks'
import ScoreGrid from './ScoreGrid'

type CnmcProposal = {
  cnmc_code: string
  cnmc_id: number
  mapping_id?: number
  material_type: string
  category: string
  standardized_description: string
  scores: MatchScores
  critical_checks: CriticalCheck[]
  engine_decision: 'HIGH_CONFIDENCE' | 'REVIEW' | 'DIFFERENT'
  final_score: number
  canonical_score: number
  strongest_member_score?: number | null
  strongest_member?: {
    material_id?: number
    cpse?: string
    material_code?: string
    description?: string
    final_score?: number
  } | null
  member_count: number
  best_score?: number | null
  second_best_score?: number | null
  score_margin?: number | null
}

type CnmcMatchModalProps = {
  material: Material | null
  onClose: () => void
  onAttached?: () => void
}

export default function CnmcMatchModal({ material, onClose, onAttached }: CnmcMatchModalProps) {
  const { isDataSteward } = useAuth()
  const [proposals, setProposals] = useState<CnmcProposal[]>([])
  const [marginInfo, setMarginInfo] = useState<{
    best_score?: number | null
    second_best_score?: number | null
    score_margin?: number | null
  }>({})
  const [loading, setLoading] = useState(true)
  const [attachingId, setAttachingId] = useState<number | null>(null)
  const [attachedIds, setAttachedIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!material) return

    let active = true
    setLoading(true)
    setError(null)
    setMessage(null)

    api.findCnmcCandidates({
      id: material.id,
      cpse: material.cpse,
      material_code: material.material_code,
      description: material.description,
      category: material.category,
      material_grade: material.material_grade || undefined,
    })
      .then((res) => {
        if (active) {
          setProposals(res.candidates as CnmcProposal[])
          setMarginInfo({
            best_score: res.best_score,
            second_best_score: res.second_best_score,
            score_margin: res.score_margin,
          })
          setLoading(false)
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to retrieve CNMC proposals')
          setLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [material])

  if (!material) return null

  const handleAttach = async (proposal: CnmcProposal) => {
    if (!proposal.mapping_id || !material.id) return

    try {
      setAttachingId(proposal.mapping_id)
      setError(null)
      await api.attachMaterialToMapping(proposal.mapping_id, material.id)
      setAttachedIds((prev) => new Set(prev).add(proposal.mapping_id!))
      setMessage(`Material ${material.material_code} successfully attached to ${proposal.cnmc_code}.`)
      onAttached?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to attach material to CNMC mapping')
    } finally {
      setAttachingId(null)
    }
  }

  return (
    <div className="common-detail-overlay" onClick={onClose}>
      <div
        className="common-detail-modal"
        style={{ maxWidth: '780px' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="common-detail-header">
          <div>
            <div className="eyebrow">EXISTING CNMC MATCHING</div>
            <h2>CNMC Proposals for {material.material_code}</h2>
            <p>
              {material.cpse} · {material.description}
            </p>
          </div>
          <button
            type="button"
            className="common-close-button"
            onClick={onClose}
            title="Close modal"
          >
            ×
          </button>
        </div>

        <div className="common-detail-body" style={{ overflowY: 'auto', padding: '24px 28px' }}>
          {message && (
            <div className="common-info-banner" style={{ marginBottom: '1.25rem' }}>
              <div className="common-info-icon">✓</div>
              <div>
                <strong>Success</strong>
                <p>{message}</p>
              </div>
            </div>
          )}

          {error && (
            <div className="mapping-info-banner" style={{ marginBottom: '1.25rem' }}>
              <div className="mapping-info-icon">!</div>
              <div>
                <strong>Error</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {/* Source Material Profile Card */}
          <div
            style={{
              padding: '16px 20px',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-default)',
              marginBottom: '24px',
            }}
          >
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
              <span className="mapping-cpse">{material.cpse}</span>
              <span className="mapping-code">{material.material_code}</span>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Category: <strong>{material.category}</strong>
              </span>
              {material.material_grade && (
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Grade: <strong>{material.material_grade}</strong>
                </span>
              )}
            </div>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
              {material.description}
            </p>
          </div>

          {/* Margin Observability Summary (when multiple candidates) */}
          {marginInfo.best_score != null && proposals.length > 1 && (
            <div
              style={{
                marginBottom: '20px',
                padding: '12px 16px',
                borderRadius: 'var(--radius-md)',
                background: '#f8fafc',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '12px',
              }}
            >
              <div style={{ display: 'flex', gap: '16px' }}>
                <span>
                  Best Match: <strong>{formatPercent(marginInfo.best_score, 1)}</strong>
                </span>
                {marginInfo.second_best_score != null && (
                  <span>
                    Second Best: <strong>{formatPercent(marginInfo.second_best_score, 1)}</strong>
                  </span>
                )}
              </div>
              {marginInfo.score_margin != null && (
                <span style={{ color: marginInfo.score_margin >= 0.1 ? '#10b981' : '#f59e0b', fontWeight: 600 }}>
                  Margin Delta: +{(marginInfo.score_margin * 100).toFixed(1)}%
                </span>
              )}
            </div>
          )}

          {/* Proposals List */}
          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Searching established CNMC registry…
            </div>
          ) : proposals.length === 0 ? (
            <div
              style={{
                padding: '36px 20px',
                textAlign: 'center',
                background: 'var(--bg-surface-subtle)',
                borderRadius: 'var(--radius-lg)',
                border: '1px dashed var(--border-default)',
              }}
            >
              <h3 style={{ fontSize: '15px', color: 'var(--text-primary)', marginBottom: '6px' }}>
                No Matching CNMCs Found
              </h3>
              <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', margin: 0 }}>
                No existing registered CNMCs met the similarity threshold (score ≥ 0.50). This material will form a
                new CNMC cluster during standard harmonization.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {proposals.map((proposal) => {
                const isAttached = proposal.mapping_id ? attachedIds.has(proposal.mapping_id) : false
                const isAttaching = proposal.mapping_id === attachingId

                return (
                  <div
                    key={proposal.cnmc_code}
                    style={{
                      border: '1px solid var(--border-default)',
                      borderRadius: 'var(--radius-lg)',
                      background: '#ffffff',
                      padding: '20px',
                      boxShadow: 'var(--shadow-xs)',
                    }}
                  >
                    {/* Proposal Header */}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        marginBottom: '14px',
                        gap: '12px',
                        flexWrap: 'wrap',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '4px' }}>
                          <span className="nmc-code" style={{ fontSize: '13px' }}>
                            {proposal.cnmc_code}
                          </span>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                            {proposal.category}
                          </span>
                        </div>
                        <h4 style={{ margin: 0, fontSize: '14px', color: 'var(--text-primary)' }}>
                          {proposal.standardized_description}
                        </h4>
                      </div>

                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <Badge
                          variant={
                            proposal.engine_decision === 'HIGH_CONFIDENCE'
                              ? 'success'
                              : proposal.engine_decision === 'DIFFERENT'
                                ? 'neutral'
                                : 'review'
                          }
                        >
                          {proposal.engine_decision}
                        </Badge>
                        <span
                          style={{
                            fontSize: '12px',
                            fontFamily: 'var(--font-mono)',
                            fontWeight: 700,
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-sm)',
                            background: '#f1f5f9',
                            color: '#1e293b',
                          }}
                        >
                          {formatPercent(proposal.final_score, 0)} Match
                        </span>
                      </div>
                    </div>

                    {/* Canonical vs Member Evidence Comparison */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: proposal.strongest_member ? '1fr 1fr' : '1fr',
                        gap: '12px',
                        marginBottom: '16px',
                        background: 'var(--bg-surface-subtle)',
                        padding: '12px 16px',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '12px',
                      }}
                    >
                      <div>
                        <span style={{ color: 'var(--text-muted)', display: 'block' }}>Canonical Profile Score</span>
                        <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                          {formatPercent(proposal.canonical_score, 0)}
                        </strong>
                      </div>
                      {proposal.strongest_member && (
                        <div>
                          <span style={{ color: 'var(--text-muted)', display: 'block' }}>
                            Strongest Member ({proposal.strongest_member.cpse})
                          </span>
                          <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                            {formatPercent(proposal.strongest_member.final_score ?? 0, 0)} ·{' '}
                            <span className="mapping-code" style={{ fontSize: '11px' }}>
                              {proposal.strongest_member.material_code}
                            </span>
                          </strong>
                        </div>
                      )}
                    </div>

                    {/* Critical Technical Gates */}
                    <div style={{ marginBottom: '16px' }}>
                      <CriticalChecks checks={proposal.critical_checks} />
                    </div>

                    {/* Detailed Similarity Scores */}
                    <div style={{ marginBottom: '16px' }}>
                      <ScoreGrid scores={proposal.scores} />
                    </div>

                    {/* Action Bar */}
                    {isDataSteward && proposal.mapping_id && (
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          paddingTop: '12px',
                          borderTop: '1px solid var(--border-subtle)',
                        }}
                      >
                        <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                          {proposal.member_count} participating CPSE source(s) in this mapping cluster
                        </span>
                        {isAttached ? (
                          <span style={{ fontSize: '12px', color: 'var(--success, #16a34a)', fontWeight: 600 }}>
                            ✓ Attached to Mapping
                          </span>
                        ) : (
                          <Button
                            variant="secondary"
                            disabled={isAttaching}
                            onClick={() => handleAttach(proposal)}
                            style={{ fontSize: '12px', padding: '6px 14px' }}
                          >
                            {isAttaching ? 'Attaching…' : 'Attach to This CNMC'}
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
