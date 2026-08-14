"""Declarative research plan for an earnings event.

This module deliberately contains policy, not network calls.  The same plan can
be executed by the current Python jobs, a Cloudflare Workflow, or a local QA
runner without changing what evidence is required at each stage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence, Tuple


SCHEMA_VERSION = "earnings-research-v1"


# Discovery and document retrieval are different jobs.  LLMLayer is always the
# first attempt.  TinyFish precedes Tavily for full-document work because it is
# the stronger last-mile page fetcher; Tavily remains a graceful fallback.
_PROVIDER_WATERFALLS: Dict[str, Tuple[str, ...]] = {
    "discovery": ("llmlayer", "tavily", "tinyfish"),
    "primary_source": ("llmlayer", "tinyfish", "tavily"),
    "transcript": ("llmlayer", "tinyfish", "tavily"),
}


def provider_waterfall(kind: str = "discovery", include_exa: bool = False) -> Tuple[str, ...]:
    """Return the provider order for a research job.

    Exa is opt-in and, when enabled, is still placed behind LLMLayer so the
    primary-provider contract cannot be accidentally changed by a call site.
    """
    if kind not in _PROVIDER_WATERFALLS:
        raise ValueError(f"Unknown research kind: {kind}")
    ordered = list(_PROVIDER_WATERFALLS[kind])
    if include_exa:
        ordered.insert(1, "exa")
    return tuple(ordered)


def classify_provider_error(error: BaseException) -> str:
    """Classify provider failures for retry/circuit-breaker decisions."""
    message = str(error).lower()
    if "http 432" in message or "http 433" in message:
        return "quota_exhausted"
    if "http 401" in message:
        return "authentication"
    if "http 403" in message:
        return "forbidden"
    if "http 429" in message:
        return "rate_limited"
    if "timeout" in message:
        return "timeout"
    if "network error" in message:
        return "network"
    return "provider_error"


@dataclass(frozen=True)
class ResearchStage:
    key: str
    objective: str
    depends_on: Tuple[str, ...]
    source_priority: Tuple[str, ...]
    required_outputs: Tuple[str, ...]
    quality_gates: Tuple[str, ...]
    failure_mode: str
    parallel_group: str = ""


@dataclass(frozen=True)
class EvidenceRule:
    field: str
    authoritative_sources: Tuple[str, ...]
    rule: str


EVIDENCE_CONTRACT: Tuple[EvidenceRule, ...] = (
    EvidenceRule(
        "revenue_actual",
        ("SEC XBRL", "filed earnings-release exhibit", "company earnings release"),
        "Require period, currency, unit, GAAP/non-GAAP label, value, and source URL; never take the value from commentary alone.",
    ),
    EvidenceRule(
        "revenue_consensus",
        ("captured pre-earnings consensus snapshot",),
        "Persist the estimate and captured_at timestamp before the report; never compare an actual with a post-report rolled estimate.",
    ),
    EvidenceRule(
        "eps_actual_and_consensus",
        ("company earnings release", "captured pre-earnings consensus snapshot"),
        "Keep GAAP and adjusted EPS separate and only compute beat/miss for definition-matched values.",
    ),
    EvidenceRule(
        "guidance",
        ("company earnings release", "investor deck", "prepared remarks", "analyst Q&A"),
        "Preserve range, period, definition, and management qualifiers; code computes range midpoints and deltas.",
    ),
    EvidenceRule(
        "transcript_interpretation",
        ("prepared remarks", "analyst Q&A"),
        "Keep prepared remarks and Q&A in separate prompt budgets; use transcript text to explain results, not replace filed financial facts.",
    ),
    EvidenceRule(
        "market_reaction",
        ("session-aware market data",),
        "Select premarket, regular, or postmarket values from the provider's live market state and retain the observation timestamp.",
    ),
)


def _identity_stage() -> ResearchStage:
    return ResearchStage(
        key="resolve_event_identity",
        objective="Resolve ticker, issuer, report timestamp, fiscal period, and before/after-market session.",
        depends_on=(),
        source_priority=("earnings calendar", "company IR calendar", "SEC submissions"),
        required_outputs=("ticker", "company", "report_date", "report_time", "fiscal_period"),
        quality_gates=("issuer matches ticker", "fiscal period is dated rather than inferred from calendar quarter"),
        failure_mode="stop",
    )


def _pre_stages() -> Tuple[ResearchStage, ...]:
    return (
        _identity_stage(),
        ResearchStage(
            key="capture_consensus",
            objective="Freeze revenue and EPS expectations before the provider rolls to the next period.",
            depends_on=("resolve_event_identity",),
            source_priority=("calendar estimate", "market-data consensus"),
            required_outputs=("revenue_consensus", "eps_consensus", "period_end", "captured_at"),
            quality_gates=("period matches resolved fiscal period", "capture is earlier than report timestamp"),
            failure_mode="continue_without_beat_miss",
            parallel_group="pre_inputs",
        ),
        ResearchStage(
            key="build_prior_period_baseline",
            objective="Collect comparable prior-quarter actuals, margins, CapEx, and company guidance.",
            depends_on=("resolve_event_identity",),
            source_priority=("SEC XBRL", "prior earnings release", "investor deck"),
            required_outputs=("prior_revenue", "prior_eps", "prior_guidance", "source_provenance"),
            quality_gates=("same metric definition", "currency and units normalized", "segment values cannot exceed company total"),
            failure_mode="degrade_missing_fields",
            parallel_group="pre_inputs",
        ),
        ResearchStage(
            key="research_preview_catalysts",
            objective="Find management commitments, estimate revisions, and questions that define the setup.",
            depends_on=("resolve_event_identity",),
            source_priority=("LLMLayer", "company IR", "recent SEC filings", "fallback search providers"),
            required_outputs=("catalysts", "risks", "questions_to_answer", "source_urls"),
            quality_gates=("LLMLayer attempted first", "every material claim has a source URL"),
            failure_mode="degrade_to_primary_sources",
            parallel_group="pre_inputs",
        ),
        _reconcile_stage(("capture_consensus", "build_prior_period_baseline", "research_preview_catalysts")),
        _synthesis_stage("pre"),
        _publish_stage("pre"),
    )


def _post_stages() -> Tuple[ResearchStage, ...]:
    return (
        _identity_stage(),
        ResearchStage(
            key="collect_official_results",
            objective="Extract revenue, EPS, margins, segment results, guidance, and official links.",
            depends_on=("resolve_event_identity",),
            source_priority=("SEC XBRL", "8-K exhibit", "company earnings release", "investor deck"),
            required_outputs=("actuals", "guidance", "official_links", "claim_provenance"),
            quality_gates=("period and definition match", "revenue anchored to a primary source", "math performed in code"),
            failure_mode="retry_then_stop",
            parallel_group="post_inputs",
        ),
        ResearchStage(
            key="fetch_transcript",
            objective="Acquire the real call text and retain focused prepared-remarks and analyst-Q&A excerpts.",
            depends_on=("resolve_event_identity",),
            source_priority=("LLMLayer", "TinyFish", "Tavily"),
            required_outputs=("transcript_url", "prepared_excerpt", "qa_excerpt", "provider"),
            quality_gates=("LLMLayer attempted first", "document mentions issuer", "report period matches", "substantial full text rather than snippet"),
            failure_mode="continue_without_transcript",
            parallel_group="post_inputs",
        ),
        ResearchStage(
            key="capture_market_reaction",
            objective="Measure the settled reaction for the reporter's actual market session.",
            depends_on=("resolve_event_identity",),
            source_priority=("session-aware market data",),
            required_outputs=("reference_price", "reaction_price", "reaction_pct", "observed_at", "market_state"),
            quality_gates=("market state selects the price field", "observation follows the report"),
            failure_mode="defer_until_session_available",
            parallel_group="post_inputs",
        ),
        _reconcile_stage(("collect_official_results", "fetch_transcript", "capture_market_reaction")),
        _synthesis_stage("post"),
        _publish_stage("post"),
    )


def _reconcile_stage(dependencies: Sequence[str]) -> ResearchStage:
    return ResearchStage(
        key="reconcile_evidence",
        objective="Build a claim ledger, normalize definitions, and resolve conflicts before prose generation.",
        depends_on=tuple(dependencies),
        source_priority=("primary-source facts", "dated consensus snapshot", "transcript interpretation", "secondary context"),
        required_outputs=("claim_ledger", "unresolved_conflicts", "quality_score"),
        quality_gates=("primary sources win conflicts", "all material figures have provenance", "missing is not converted to zero"),
        failure_mode="stop_on_material_conflict",
    )


def _synthesis_stage(mode: str) -> ResearchStage:
    return ResearchStage(
        key="synthesize_brief",
        objective=f"Write the {mode}-earnings brief from the reconciled claim ledger.",
        depends_on=("reconcile_evidence",),
        source_priority=("reconciled claim ledger",),
        required_outputs=("structured_brief", "inline_citations", "official_links"),
        quality_gates=("no unsupported figures", "reader-facing prose contains the important structured facts"),
        failure_mode="revise_once_then_quarantine",
    )


def _publish_stage(mode: str) -> ResearchStage:
    return ResearchStage(
        key="review_archive_and_deliver",
        objective="Run deterministic checks, archive idempotently, and deliver only an approved brief.",
        depends_on=("synthesize_brief",),
        source_priority=("deterministic guardrails", "LLM reviewer"),
        required_outputs=("review_result", "archive_key", "delivery_status"),
        quality_gates=("idempotency key exists", "archive succeeds before send", "dry-run and native-send flags honored"),
        failure_mode="quarantine_no_send",
    )


def build_earnings_research_plan(
    ticker: str,
    company: str,
    report_date: str,
    mode: str,
    report_time: str = "",
) -> Dict[str, Any]:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"pre", "post"}:
        raise ValueError("mode must be 'pre' or 'post'")
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("ticker is required")
    if not report_date.strip():
        raise ValueError("report_date is required")

    stages = _pre_stages() if normalized_mode == "pre" else _post_stages()
    instance_id = f"earnings-{normalized_ticker.lower()}-{report_date.strip()}-{normalized_mode}-v1"
    return {
        "schema_version": SCHEMA_VERSION,
        "instance_id": instance_id,
        "subject": {
            "ticker": normalized_ticker,
            "company": company.strip() or normalized_ticker,
            "report_date": report_date.strip(),
            "report_time": report_time.strip(),
        },
        "mode": normalized_mode,
        "provider_waterfalls": {
            kind: list(provider_waterfall(kind)) for kind in _PROVIDER_WATERFALLS
        },
        "evidence_contract": [asdict(rule) for rule in EVIDENCE_CONTRACT],
        "stages": [asdict(stage) for stage in stages],
    }

