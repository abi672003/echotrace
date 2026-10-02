from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ClusterType = Literal[
    "coordinated_paraphrase_campaign",
    "form_letter",
    "organic_agreement",
    "insufficient_evidence",
]
ReviewDecision = Literal["confirmed", "rejected", "unsure"]
Confidence = Literal["low", "medium", "high"]
ProviderKeyStatus = Literal["configured", "missing"]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorDetail


class ProviderStatus(BaseModel):
    regulations: ProviderKeyStatus
    gemini: ProviderKeyStatus
    groq: ProviderKeyStatus


class HealthOut(BaseModel):
    status: str
    db: str
    providers: ProviderStatus


class DocketOut(BaseModel):
    id: str
    agency_id: str | None
    title: str | None
    source: str
    remote_comment_count: int | None
    ingested_count: int
    skipped_count: int
    ingest_status: str
    ingest_error: str | None
    last_ingested_at: datetime | None
    created_at: datetime


class DocketCreate(BaseModel):
    docket_id: str = Field(pattern=r"^[A-Z0-9-]+$")
    max_comments: int = 500


class SampleOut(BaseModel):
    name: str
    docket_id: str
    count: int


class DocumentOut(BaseModel):
    id: int
    docket_id: str
    external_id: str
    title: str | None
    submitter_label: str
    submitter_hash: str
    organization: str | None
    text: str
    word_count: int
    posted_at: datetime | None
    url: str | None
    created_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int


class AnalysisCreate(BaseModel):
    mode: Literal["docket", "text"]
    docket_id: str
    text: str | None = None


class AnalysisCreateOut(BaseModel):
    analysis_id: str


class AnalysisStepOut(BaseModel):
    name: str
    status: str
    detail: str | None
    started_at: datetime | None
    finished_at: datetime | None


class AnalysisUsage(BaseModel):
    llm_calls: int
    embed_calls: int


class ClusterMetrics(BaseModel):
    reword_index: float
    burst_24h: float
    name_diversity: float
    ai_agg: float


class ClusterSummary(BaseModel):
    id: int
    size: int
    campaign_score: float
    preliminary_type: ClusterType
    verdict_type: ClusterType | None
    confidence: Confidence | None
    review_status: str
    metrics: ClusterMetrics
    medoid_excerpt: str


class AnalysisOut(BaseModel):
    id: str
    mode: str
    docket_id: str
    status: str
    steps: list[AnalysisStepOut]
    summary: str | None
    usage: AnalysisUsage
    clusters: list[ClusterSummary]
    created_at: datetime
    finished_at: datetime | None


class AnalysisSummary(BaseModel):
    id: str
    mode: str
    docket_id: str
    status: str
    created_at: datetime
    finished_at: datetime | None


class AgentTraceOut(BaseModel):
    step_no: int
    action: str
    args: dict
    observation: dict
    cluster_id: int | None
    created_at: datetime


class ClusterMemberOut(BaseModel):
    document_id: int
    sim_to_medoid: float
    lex_to_medoid: float
    ai_score: float | None
    is_medoid: bool


class ClusterOut(BaseModel):
    id: int
    analysis_id: str
    size: int
    metrics: dict
    campaign_score: float
    preliminary_type: ClusterType
    verdict_type: ClusterType | None
    confidence: Confidence | None
    rationale: str | None
    cited_document_ids: list[int]
    citations_corrected: bool
    recommend_review: bool
    review_status: str
    members: list[ClusterMemberOut]


class GraphNode(BaseModel):
    id: int
    excerpt: str
    submitter_label: str
    posted_at: datetime | None
    ai_score: float | None
    sim: float
    lex: float
    is_medoid: bool


class GraphEdge(BaseModel):
    source: int
    target: int
    sim: float
    lex: float


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ReviewIn(BaseModel):
    decision: ReviewDecision
    note: str | None = None


class ReviewOut(BaseModel):
    id: int
    cluster_id: int
    decision: ReviewDecision
    note: str | None
    created_at: datetime


class SharedSpan(BaseModel):
    a_start: int
    a_end: int
    b_start: int
    b_end: int
    text: str


class CompareOut(BaseModel):
    a: int
    b: int
    sem: float
    lex: float
    shared: list[SharedSpan]
