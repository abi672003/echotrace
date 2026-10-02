import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from './client'
import type {
  AgentTraceOut,
  AnalysisCreate,
  AnalysisCreateOut,
  AnalysisOut,
  AnalysisSummary,
  ClusterOut,
  CompareOut,
  DocketOut,
  DocumentListOut,
  DocumentOut,
  GraphOut,
  HealthOut,
  ReviewIn,
  ReviewOut,
  SampleOut,
} from './types'

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => apiGet<HealthOut>('/health') })
}

export function useDockets() {
  return useQuery({ queryKey: ['dockets'], queryFn: () => apiGet<DocketOut[]>('/dockets') })
}

export function useDocket(docketId: string | undefined) {
  return useQuery({
    queryKey: ['docket', docketId],
    queryFn: () => apiGet<DocketOut>(`/dockets/${docketId}`),
    enabled: !!docketId,
    refetchInterval: (query) => (query.state.data?.ingest_status === 'running' ? 3000 : false),
  })
}

export function useDocketDocuments(
  docketId: string | undefined,
  params: { limit?: number; offset?: number; q?: string } = {},
) {
  const query = new URLSearchParams()
  if (params.limit) query.set('limit', String(params.limit))
  if (params.offset) query.set('offset', String(params.offset))
  if (params.q) query.set('q', params.q)
  const qs = query.toString()
  return useQuery({
    queryKey: ['docket-documents', docketId, params],
    queryFn: () => apiGet<DocumentListOut>(`/dockets/${docketId}/documents${qs ? `?${qs}` : ''}`),
    enabled: !!docketId,
  })
}

export function useDocument(documentId: number | undefined) {
  return useQuery({
    queryKey: ['document', documentId],
    queryFn: () => apiGet<DocumentOut>(`/documents/${documentId}`),
    enabled: documentId !== undefined,
  })
}

export function useSamples() {
  return useQuery({ queryKey: ['samples'], queryFn: () => apiGet<SampleOut[]>('/samples') })
}

export function useCreateDocket() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { docket_id: string; max_comments?: number }) =>
      apiPost<DocketOut>('/dockets', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dockets'] }),
  })
}

export function useLoadSample() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sampleName: string) => apiPost<DocketOut>(`/dockets/samples/${sampleName}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dockets'] }),
  })
}

export function useAnalyses(docketId: string | undefined) {
  return useQuery({
    queryKey: ['analyses', docketId],
    queryFn: () => apiGet<AnalysisSummary[]>(`/analyses?docket_id=${docketId}`),
    enabled: !!docketId,
  })
}

export function useAnalysis(analysisId: string | undefined) {
  return useQuery({
    queryKey: ['analysis', analysisId],
    queryFn: () => apiGet<AnalysisOut>(`/analyses/${analysisId}`),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 1500 : false
    },
  })
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AnalysisCreate) => apiPost<AnalysisCreateOut>('/analyses', body),
    onSuccess: (_data, variables) =>
      queryClient.invalidateQueries({ queryKey: ['analyses', variables.docket_id] }),
  })
}

export function useAnalysisTrace(analysisId: string | undefined, clusterId?: number) {
  return useQuery({
    queryKey: ['analysis-trace', analysisId, clusterId],
    queryFn: () =>
      apiGet<AgentTraceOut[]>(
        `/analyses/${analysisId}/trace${clusterId !== undefined ? `?cluster_id=${clusterId}` : ''}`,
      ),
    enabled: !!analysisId,
  })
}

export function useCluster(clusterId: number | undefined) {
  return useQuery({
    queryKey: ['cluster', clusterId],
    queryFn: () => apiGet<ClusterOut>(`/clusters/${clusterId}`),
    enabled: clusterId !== undefined,
  })
}

export function useClusterGraph(clusterId: number | undefined, maxNodes = 60) {
  return useQuery({
    queryKey: ['cluster-graph', clusterId, maxNodes],
    queryFn: () => apiGet<GraphOut>(`/clusters/${clusterId}/graph?max_nodes=${maxNodes}`),
    enabled: clusterId !== undefined,
  })
}

export function useSubmitReview(clusterId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ReviewIn) => apiPost<ReviewOut>(`/clusters/${clusterId}/reviews`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cluster', clusterId] })
    },
  })
}

export function useCompareDocuments(a: number | undefined, b: number | undefined) {
  return useQuery({
    queryKey: ['compare', a, b],
    queryFn: () => apiGet<CompareOut>(`/documents/compare?a=${a}&b=${b}`),
    enabled: a !== undefined && b !== undefined,
  })
}
