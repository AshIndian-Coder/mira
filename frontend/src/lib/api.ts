const API_BASE = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: 'application/json',
      ...(options?.body instanceof FormData
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail =
        typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail ?? body)
    } catch {
      // ignore parse errors
    }
    throw new Error(detail || `Request failed (${response.status})`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export type Material = {
  id: number
  cpse: string
  material_code: string
  description: string
  normalized_description: string
  category: string
  unit?: string | null
  manufacturer?: string | null
  manufacturer_part_number?: string | null
  material_grade?: string | null
  parsed_specifications?: Record<string, unknown>
  other_attributes?: Record<string, unknown>
}

export type MatchScores = {
  text_similarity: number
  semantic_similarity: number
  specification_similarity: number
  material_grade_similarity: number
  other_attributes_similarity: number
  final_score: number
}

export type CriticalCheck = {
  field: string
  status: 'PASS' | 'UNKNOWN' | 'CONFLICT'
  source_value: unknown
  target_value: unknown
  reason: string
}

export type Candidate = {
  id: number
  source_material_id: number
  target_material_id: number
  source_cpse: string
  target_cpse: string
  source_code: string
  target_code: string
  source_description: string
  target_description: string
  scores: MatchScores
  critical_checks: CriticalCheck[]
  engine_decision: 'HIGH_CONFIDENCE' | 'REVIEW' | 'DIFFERENT'
  review_status: string
  reviewer_id?: string | null
  reviewer_comments?: string | null
  reviewed_at?: string | null
  created_at?: string
}

export type AnalyticsOverview = {
  total_materials: number
  cpse_count: number
  total_candidate_pairs: number
  high_confidence: number
  review_pending: number
  approved: number
  rejected: number
  automation_rate: number | null
}

export type CpseBreakdown = {
  cpse: string
  material_count: number
  candidate_pair_involvements: number
}

export type CategoryDistribution = {
  category: string
  count: number
}

export type ScoreBucket = {
  bucket: string
  count: number
}

export type AuditEvent = {
  event_type: string
  candidate_id?: number
  source_code?: string
  target_code?: string
  source_cpse?: string
  target_cpse?: string
  actor?: string
  comments?: string | null
  final_score?: number
  timestamp: string
}

export type MappingEntry = {
  material_id: number
  cpse: string
  material_code: string
  description: string
  category?: string
  material_grade?: string | null
}

export type Mapping = {
  id: number
  nmc: string
  cpse_mappings: MappingEntry[]
  cluster_size: number
  status: string
  created_at: string
}

export const api = {
  health: () => request<{ status: string; service: string }>('/health'),

  uploadMaterials: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return request<{
      status: string
      records_ingested: number
      total_materials: number
    }>('/api/materials/upload', {
      method: 'POST',
      body: formData,
    })
  },

  listMaterials: (params?: {
    query?: string
    cpse?: string
    category?: string
    skip?: number
    limit?: number
  }) => {
    const search = new URLSearchParams()
    if (params?.query) search.set('query', params.query)
    if (params?.cpse) search.set('cpse', params.cpse)
    if (params?.category) search.set('category', params.category)
    if (params?.skip != null) search.set('skip', String(params.skip))
    if (params?.limit != null) search.set('limit', String(params.limit))
    const qs = search.toString()
    return request<{
      total: number
      skip: number
      limit: number
      materials: Material[]
    }>(`/api/materials${qs ? `?${qs}` : ''}`)
  },

  materialsStats: () =>
    request<{
      total_materials: number
      cpse_count: number
      cpse_list: string[]
      category_distribution: Record<string, number>
    }>('/api/materials/stats'),

  runBatchMatching: (overwrite = false) =>
    request<{
      status: string
      materials_processed: number
      candidate_pairs_evaluated: number
      new_candidates_stored: number
      total_candidates: number
      decision_breakdown: Record<string, number>
      elapsed_ms: number
    }>('/api/matching/run-batch', {
      method: 'POST',
      body: JSON.stringify({ overwrite, max_candidates_per_material: 50 }),
    }),

  reviewQueue: (skip = 0, limit = 100) =>
    request<{
      total_pending: number
      skip: number
      limit: number
      queue: Candidate[]
    }>(`/api/review/queue?skip=${skip}&limit=${limit}`),

  reviewSummary: () =>
    request<{
      total_review_queue: number
      pending: number
      approved: number
      rejected: number
      high_confidence: number
    }>('/api/review/summary'),

  reviewAction: (
    candidateId: number,
    action: 'APPROVE' | 'REJECT',
    comments?: string,
  ) =>
    request<{ status: string; candidate: Candidate }>(
      `/api/review/queue/${candidateId}/action`,
      {
        method: 'POST',
        body: JSON.stringify({
          action,
          reviewer_comments: comments ?? null,
          user_id: 'operator_01',
        }),
      },
    ),

  analyticsOverview: () =>
    request<AnalyticsOverview>('/api/analytics/overview'),

  analyticsByCpse: () =>
    request<{ cpse_breakdown: CpseBreakdown[] }>('/api/analytics/by-cpse'),

  analyticsCategories: () =>
    request<{ category_distribution: CategoryDistribution[] }>(
      '/api/analytics/categories',
    ),

  analyticsScores: () =>
    request<{ total_candidates: number; score_histogram: ScoreBucket[] }>(
      '/api/analytics/scores',
    ),

  listMappings: () =>
    request<{ total: number; mappings: Mapping[] }>('/api/mappings'),

  generateMappings: () =>
    request<{
      status: string
      mappings_created: number
      total_mappings: number
      mappings: Mapping[]
      message?: string
    }>('/api/mappings/generate', { method: 'POST' }),

  exportMappingsFlat: () =>
    request<{
      total_rows: number
      rows: Array<{
        nmc: string
        cpse: string
        cpse_material_code: string
        description: string
        category?: string
        material_grade?: string | null
      }>
    }>('/api/mappings/export/flat'),

  listAudit: (skip = 0, limit = 100) =>
    request<{ total: number; events: AuditEvent[] }>(
      `/api/audit?skip=${skip}&limit=${limit}`,
    ),

  exportAudit: () =>
    request<{ total: number; events: AuditEvent[] }>('/api/audit/export'),
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

export function formatNumber(value: number): string {
  return value.toLocaleString()
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
