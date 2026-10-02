from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    AgentTrace,
    AiScoreCache,
    Analysis,
    AnalysisStep,
    Cluster,
    ClusterMember,
    Docket,
    Document,
    EmbeddingCache,
    Review,
)


def test_insert_and_read_one_row_per_table() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        docket = Docket(id="EPA-HQ-OAR-2021-0317", source="sample")
        session.add(docket)
        session.commit()
        docket_id = docket.id

        document = Document(
            docket_id=docket_id,
            external_id="EPA-HQ-OAR-2021-0317-0001",
            submitter_label="Jane Doe",
            submitter_hash="hash123",
            text="This is a comment.",
            text_hash="texthash123",
            word_count=5,
        )
        session.add(document)
        session.commit()
        document_id = document.id
        text_hash = document.text_hash

        embedding_model = "gemini-embedding-001"
        ai_score_model = "llama-3.3-70b-versatile"
        session.add(
            EmbeddingCache(text_hash=text_hash, model=embedding_model, dim=3, vector=b"\x00\x01\x02")
        )
        session.add(
            AiScoreCache(text_hash=text_hash, model=ai_score_model, score=0.5, reason="test reason")
        )
        session.commit()

        analysis = Analysis(
            id="analysis1",
            mode="docket",
            docket_id=docket_id,
            params={"SIM_EDGE": 0.86},
        )
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id

        session.add(AnalysisStep(analysis_id=analysis_id, name="normalize", status="done"))

        cluster = Cluster(
            analysis_id=analysis_id,
            medoid_document_id=document_id,
            size=1,
            metrics={"mean_sem": 1.0},
            campaign_score=0.5,
            preliminary_type="insufficient_evidence",
        )
        session.add(cluster)
        session.commit()
        cluster_id = cluster.id

        session.add(
            ClusterMember(
                cluster_id=cluster_id,
                document_id=document_id,
                sim_to_medoid=1.0,
                lex_to_medoid=1.0,
                is_medoid=True,
            )
        )
        session.add(
            AgentTrace(
                analysis_id=analysis_id,
                cluster_id=cluster_id,
                step_no=1,
                action="family_summary",
                args={},
                observation={"size": 1},
            )
        )
        session.add(Review(cluster_id=cluster_id, decision="confirmed", note="looks right"))
        session.commit()

    with Session(engine) as session:
        assert session.get(Docket, docket_id) is not None
        assert session.get(Document, document_id) is not None
        assert session.get(EmbeddingCache, (text_hash, embedding_model)) is not None
        assert session.get(AiScoreCache, (text_hash, ai_score_model)) is not None
        assert session.get(Analysis, analysis_id) is not None
        assert (
            session.exec(select(AnalysisStep).where(AnalysisStep.analysis_id == analysis_id)).first()
            is not None
        )
        assert session.get(Cluster, cluster_id) is not None
        assert session.get(ClusterMember, (cluster_id, document_id)) is not None
        assert (
            session.exec(select(AgentTrace).where(AgentTrace.analysis_id == analysis_id)).first()
            is not None
        )
        assert (
            session.exec(select(Review).where(Review.cluster_id == cluster_id)).first() is not None
        )
