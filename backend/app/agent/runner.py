import json

from sqlmodel import Session, select

from app.agent.citations import extract_ids_from_observation, validate_citations
from app.agent.prompts import render_system_prompt, render_tool_specs
from app.agent.tools import TOOL_FUNCTIONS, TOOL_SPECS, ToolContext, truncate_observation
from app.config import get_settings
from app.models import AgentTrace, Cluster, ClusterMember
from app.services.llm import LLM, LLMJSONError

FALLBACK_RATIONALE = "Automatic review unavailable."


async def review_family(
    session: Session,
    llm: LLM,
    cluster: Cluster,
    docket_id: str,
    max_steps: int | None = None,
) -> Cluster:
    """Runs the provider-agnostic turn loop (§7) for one family: at most `max_steps`
    (default `AGENT_MAX_STEPS`) LLM turns, each one JSON object
    `{"thought","action","args"}`, writing an `AgentTrace` row per tool step. Ends by
    either applying a citation-validated verdict or falling back to the preliminary
    type with `confidence="low"` — on an unrecoverable invalid-JSON reply, or on
    exhausting the step budget without a `submit_verdict` call."""
    settings = get_settings()
    max_steps = max_steps if max_steps is not None else settings.AGENT_MAX_STEPS

    ctx = ToolContext(session=session, cluster=cluster, docket_id=docket_id)
    family_member_ids = {
        member.document_id
        for member in session.exec(
            select(ClusterMember).where(ClusterMember.cluster_id == cluster.id)
        ).all()
    }
    seen_tool_ids: set[int] = set()

    tool_specs_text = render_tool_specs(TOOL_SPECS)
    family_summary_json = json.dumps(TOOL_FUNCTIONS["family_summary"](ctx))
    system_prompt = render_system_prompt(tool_specs_text, family_summary_json)

    messages: list[dict[str, str]] = []

    for step_no in range(1, max_steps + 1):
        try:
            turn = await llm.complete_json(system_prompt, messages, schema={})
        except LLMJSONError:
            return _apply_fallback(session, cluster)

        action = turn.get("action")
        args = turn.get("args") or {}

        if action == "submit_verdict":
            return _finalize_verdict(
                session, cluster, args, family_member_ids, seen_tool_ids, step_no
            )

        tool_fn = TOOL_FUNCTIONS.get(action)
        if tool_fn is None:
            observation = {"error": f"Unknown tool: {action!r}"}
        else:
            try:
                observation = tool_fn(ctx, **args)
            except TypeError as exc:
                observation = {"error": f"Invalid arguments for {action}: {exc}"}

        observation = truncate_observation(observation)
        seen_tool_ids |= extract_ids_from_observation(observation)

        session.add(
            AgentTrace(
                analysis_id=cluster.analysis_id,
                cluster_id=cluster.id,
                step_no=step_no,
                action=str(action),
                args=args,
                observation=observation,
            )
        )
        session.commit()

        messages.append({"role": "assistant", "content": json.dumps(turn)})
        messages.append({"role": "user", "content": json.dumps({"observation": observation})})

    return _apply_fallback(session, cluster)


def _apply_fallback(session: Session, cluster: Cluster) -> Cluster:
    cluster.verdict_type = cluster.preliminary_type
    cluster.confidence = "low"
    cluster.rationale = FALLBACK_RATIONALE
    cluster.cited_document_ids = []
    cluster.citations_corrected = False
    session.add(cluster)
    session.commit()
    return cluster


def _finalize_verdict(
    session: Session,
    cluster: Cluster,
    args: dict,
    family_member_ids: set[int],
    seen_tool_ids: set[int],
    step_no: int,
) -> Cluster:
    verdict_type = args.get("type", cluster.preliminary_type)
    confidence = args.get("confidence", "low")
    rationale = args.get("rationale", "")
    recommend_review = bool(args.get("recommend_review", True))
    cited_ids = [int(i) for i in (args.get("cited_document_ids") or [])]

    result = validate_citations(cited_ids, family_member_ids, seen_tool_ids, confidence)

    cluster.verdict_type = verdict_type
    cluster.confidence = result.confidence
    cluster.rationale = rationale
    cluster.cited_document_ids = result.cited_document_ids
    cluster.citations_corrected = result.citations_corrected
    cluster.recommend_review = recommend_review

    session.add(
        AgentTrace(
            analysis_id=cluster.analysis_id,
            cluster_id=cluster.id,
            step_no=step_no,
            action="submit_verdict",
            args=args,
            observation={"applied": True},
        )
    )
    session.add(cluster)
    session.commit()
    return cluster
