export type ClusterType =
  | 'coordinated_paraphrase_campaign'
  | 'form_letter'
  | 'organic_agreement'
  | 'insufficient_evidence'

export type Confidence = 'low' | 'medium' | 'high'
export type ProviderKeyStatus = 'configured' | 'missing'
export type ReviewDecision = 'confirmed' | 'rejected' | 'unsure'
export type AnalysisStatus = 'queued' | 'running' | 'done' | 'failed'
export type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'
export type IngestStatus = 'idle' | 'running' | 'done' | 'partial' | 'failed'
export type PipelineStepName =
  | 'normalize'
  | 'embed'
  | 'cluster'
  | 'measure'
  | 'ai_score'
  | 'aggregate'
  | 'agent'

export interface ProviderStatus {
  regulations: ProviderKeyStatus
  gemini: ProviderKeyStatus
  groq: ProviderKeyStatus
}

export interface HealthOut {
  status: string
  db: string
  providers: ProviderStatus
}

export interface DocketOut {
  id: string
  agency_id: string | null
  title: string | null
  source: string
  remote_comment_count: number | null
  ingested_count: number
  skipped_count: number
  ingest_status: IngestStatus
  ingest_error: string | null
  last_ingested_at: string | null
  created_at: string
}

export interface SampleOut {
  name: string
  docket_id: string
  count: number
}

export interface DocumentOut {
  id: number
  docket_id: string
  external_id: string
  title: string | null
  submitter_label: string
  submitter_hash: string
  organization: string | null
  text: string
  word_count: number
  posted_at: string | null
  url: string | null
  created_at: string
}

export interface DocumentListOut {
  items: DocumentOut[]
  total: number
}

export interface AnalysisCreate {
  mode: 'docket' | 'text'
  docket_id: string
  text?: string
}

export interface AnalysisCreateOut {
  analysis_id: string
}

export interface AnalysisStepOut {
  name: PipelineStepName
  status: StepStatus
  detail: string | null
  started_at: string | null
  finished_at: string | null
}

export interface AnalysisUsage {
  llm_calls: number
  embed_calls: number
}

export interface ClusterMetrics {
  reword_index: number
  burst_24h: number
  name_diversity: number
  ai_agg: number
}

export interface ClusterSummary {
  id: number
  size: number
  campaign_score: number
  preliminary_type: ClusterType
  verdict_type: ClusterType | null
  confidence: Confidence | null
  review_status: string
  metrics: ClusterMetrics
  medoid_excerpt: string
}

export interface AnalysisOut {
  id: string
  mode: string
  docket_id: string
  status: AnalysisStatus
  steps: AnalysisStepOut[]
  summary: string | null
  usage: AnalysisUsage
  clusters: ClusterSummary[]
  created_at: string
  finished_at: string | null
}

export interface AnalysisSummary {
  id: string
  mode: string
  docket_id: string
  status: AnalysisStatus
  created_at: string
  finished_at: string | null
}

export interface AgentTraceOut {
  step_no: number
  action: string
  args: Record<string, unknown>
  observation: Record<string, unknown>
  cluster_id: number | null
  created_at: string
}

export interface ClusterMemberOut {
  document_id: number
  sim_to_medoid: number
  lex_to_medoid: number
  ai_score: number | null
  is_medoid: boolean
}

export interface FullClusterMetrics {
  mean_sem: number
  mean_lex: number
  reword_index: number
  exact_dup_share: number
  burst_24h: number
  name_diversity: number
  anon_share: number
  ai_agg: number
}

export interface ClusterOut {
  id: number
  analysis_id: string
  size: number
  metrics: FullClusterMetrics
  campaign_score: number
  preliminary_type: ClusterType
  verdict_type: ClusterType | null
  confidence: Confidence | null
  rationale: string | null
  cited_document_ids: number[]
  citations_corrected: boolean
  recommend_review: boolean
  review_status: string
  members: ClusterMemberOut[]
}

export interface GraphNode {
  id: number
  excerpt: string
  submitter_label: string
  posted_at: string | null
  ai_score: number | null
  sim: number
  lex: number
  is_medoid: boolean
}

export interface GraphEdge {
  source: number
  target: number
  sim: number
  lex: number
}

export interface GraphOut {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ReviewIn {
  decision: ReviewDecision
  note?: string
}

export interface ReviewOut {
  id: number
  cluster_id: number
  decision: ReviewDecision
  note: string | null
  created_at: string
}

export interface SharedSpan {
  a_start: number
  a_end: number
  b_start: number
  b_end: number
  text: string
}

export interface CompareOut {
  a: number
  b: number
  sem: number
  lex: number
  shared: SharedSpan[]
}
