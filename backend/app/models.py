from datetime import datetime, timezone

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Docket(SQLModel, table=True):
    id: str = Field(primary_key=True)  # e.g. "EPA-HQ-OAR-2021-0317"
    agency_id: str | None = None
    title: str | None = None
    source: str  # "regulations_gov" | "sample"
    remote_comment_count: int | None = None
    ingested_count: int = 0
    skipped_count: int = 0
    ingest_status: str = "idle"  # idle|running|done|partial|failed
    ingest_error: str | None = None
    last_ingested_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Document(SQLModel, table=True):  # one public comment
    id: int | None = Field(default=None, primary_key=True)
    docket_id: str = Field(foreign_key="docket.id", index=True)
    external_id: str = Field(unique=True)  # Regulations.gov comment ID
    title: str | None = None
    submitter_label: str  # display name as provided, "Anonymous" if none
    submitter_hash: str  # sha256(lower(name)) for diversity metrics
    organization: str | None = None
    text: str
    text_hash: str = Field(index=True)
    word_count: int
    posted_at: datetime | None = Field(default=None, index=True)
    url: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class EmbeddingCache(SQLModel, table=True):
    text_hash: str = Field(primary_key=True)
    model: str = Field(primary_key=True)
    dim: int
    vector: bytes  # float32, L2-normalised
    created_at: datetime = Field(default_factory=_utcnow)


class AiScoreCache(SQLModel, table=True):
    text_hash: str = Field(primary_key=True)
    model: str = Field(primary_key=True)
    score: float
    reason: str
    created_at: datetime = Field(default_factory=_utcnow)


class Analysis(SQLModel, table=True):
    id: str = Field(primary_key=True)  # uuid4 hex
    mode: str  # "docket" | "text"
    docket_id: str = Field(foreign_key="docket.id", index=True)
    input_text: str | None = None
    status: str = "queued"  # queued|running|done|failed
    current_step: str | None = None
    error: str | None = None
    summary: str | None = None  # agent's docket-level summary
    params: dict = Field(sa_column=Column(JSON))  # thresholds + model names used
    llm_calls: int = 0
    embed_calls: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None


class AnalysisStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    analysis_id: str = Field(foreign_key="analysis.id", index=True)
    name: str  # normalize|embed|cluster|measure|ai_score|aggregate|agent
    status: str  # pending|running|done|failed|skipped
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Cluster(SQLModel, table=True):  # a "family"
    id: int | None = Field(default=None, primary_key=True)
    analysis_id: str = Field(foreign_key="analysis.id", index=True)
    medoid_document_id: int = Field(foreign_key="document.id")
    size: int
    metrics: dict = Field(sa_column=Column(JSON))  # Â§4.5 keys
    campaign_score: float
    preliminary_type: str
    verdict_type: str | None = None  # set by agent (same enum)
    confidence: str | None = None  # low|medium|high
    rationale: str | None = None
    cited_document_ids: list = Field(sa_column=Column(JSON), default=[])
    citations_corrected: bool = False
    recommend_review: bool = True
    review_status: str = "unreviewed"  # unreviewed|confirmed|rejected|unsure


class ClusterMember(SQLModel, table=True):
    cluster_id: int = Field(foreign_key="cluster.id", primary_key=True)
    document_id: int = Field(foreign_key="document.id", primary_key=True)
    sim_to_medoid: float
    lex_to_medoid: float
    ai_score: float | None = None
    is_medoid: bool = False


class AgentTrace(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    analysis_id: str = Field(foreign_key="analysis.id", index=True)
    cluster_id: int | None = None
    step_no: int
    action: str
    args: dict = Field(sa_column=Column(JSON))
    observation: dict = Field(sa_column=Column(JSON))  # truncated to 4 KB
    created_at: datetime = Field(default_factory=_utcnow)


class Review(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    cluster_id: int = Field(foreign_key="cluster.id", index=True)
    decision: str  # confirmed|rejected|unsure
    note: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
