from typing import Literal

from pydantic import BaseModel, Field

from app.agents.common import EvidenceLedger, run_tool_agent
from app.agents.schemas import EscalationResult, TraceabilityResult, TriageResult


class Decision(BaseModel):
    summary: str = Field(min_length=10, max_length=1200)
    rationale: list[str] = Field(min_length=1, max_length=8)
    confidence: Literal["low", "medium", "high"]
    follow_up_questions: list[str] = Field(default_factory=list, max_length=5)


class TriageDecision(Decision):
    selected_product_id: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    recommendation: Literal["request_information", "retailer_review", "forward_to_importer"]


class TraceDecision(Decision):
    selected_product_id: str | None = None
    selected_batch_id: str | None = None
    proposal_type: Literal["request_information", "retailer_inspections"]
    match_method: Literal["exact_sku", "exact_name", "known_alias", "unresolved"]
    missing: list[str] = Field(default_factory=list)


class EscalationDecision(Decision):
    followup_retailer_ids: list[str] = Field(default_factory=list, max_length=100)
    recommendation: Literal[
        "request_more_retailer_checks", "prepare_manufacturer_escalation", "continue_monitoring"
    ]
    manufacturer_questions: list[str] = Field(min_length=1, max_length=8)


def assessment(decision: Decision) -> dict:
    return {
        "summary": decision.summary,
        "confidence": decision.confidence,
        "unanswered_questions": decision.follow_up_questions,
    }


def finalize_triage(decision: TriageDecision, ledger: EvidenceLedger) -> dict:
    case = ledger.read("get_case", case_id=ledger.case_id)
    ledger.read("search_products")
    products = ledger.products()
    if decision.selected_product_id and decision.selected_product_id not in products:
        raise ValueError("Selected product was not returned by an MCP catalogue search")
    related = []
    if decision.selected_product_id and case.get("batch_number"):
        related = ledger.read(
            "find_related_reports",
            product_id=decision.selected_product_id,
            batch_number=case["batch_number"],
        )
    if decision.recommendation != "request_information" and (
        not decision.selected_product_id or not case.get("batch_number") or not case.get("retailer")
    ):
        raise ValueError("Missing product, batch or retailer requires an information request")
    return TriageResult(
        case_id=ledger.case_id,
        possible_product_ids=list(products),
        reported_batch_number=case.get("batch_number"),
        related_case_ids=[item["case_id"] for item in related],
        missing_fields=decision.missing_fields,
        follow_up_questions=decision.follow_up_questions,
        recommendation=decision.recommendation,
        confidence=decision.confidence,
        rationale=decision.rationale,
        evidence_references=[ledger.case_id, *products],
        ai_assessment=assessment(decision),
    ).model_dump()


def finalize_trace(decision: TraceDecision, ledger: EvidenceLedger) -> dict:
    case = ledger.read("get_case", case_id=ledger.case_id)
    ledger.read("search_products")
    product = ledger.products().get(decision.selected_product_id)
    batch = ledger.batches().get(decision.selected_batch_id)
    if decision.selected_product_id and not product:
        raise ValueError("Selected product must come from the MCP catalogue")
    if decision.selected_batch_id and not batch:
        raise ValueError("Selected batch must come from get_batch")
    # Never accept a lot match without the corresponding product identity.
    if batch and (
        not product
        or batch["product_id"] != product["id"]
        or batch["batch_number"] != case.get("batch_number")
    ):
        raise ValueError("Product and lot must match the retrieved batch and case")
    if decision.proposal_type == "request_information" and not decision.missing:
        raise ValueError(
            "Information requests must identify a concrete missing traceability fact in missing. "
            "Lab confirmation is not required for tracing or proposing retailer checks."
        )
    shipments, excluded, related = [], [], []
    if decision.proposal_type == "retailer_inspections":
        if not product or not batch:
            raise ValueError("Retailer checks require a resolved product and lot")
        shipments = ledger.read("get_batch_shipments", batch_id=batch["id"])
        excluded = ledger.read("get_non_recipient_retailers", batch_id=batch["id"])
        related = ledger.read(
            "find_related_reports", product_id=product["id"], batch_number=batch["batch_number"]
        )
    return TraceabilityResult(
        type=decision.proposal_type,
        case_id=ledger.case_id,
        matched_product_id=product["id"] if product else None,
        matched_batch_id=batch["id"] if batch else None,
        match_method=decision.match_method,
        confidence=decision.confidence,
        product=product,
        batch=batch,
        retailers=shipments,
        excluded_retailers=excluded,
        related_reports=related,
        missing=decision.missing,
        rationale=decision.rationale,
        evidence_references=[
            ledger.case_id,
            *([product["id"]] if product else []),
            *([batch["id"]] if batch else []),
            *[row["shipment_id"] for row in shipments],
        ],
        ai_assessment=assessment(decision),
    ).model_dump()


def finalize_escalation(decision: EscalationDecision, ledger: EvidenceLedger) -> dict:
    case = ledger.read("get_case", case_id=ledger.case_id)
    trace = ledger.read("get_approved_traceability", case_id=ledger.case_id)
    if not trace.get("found"):
        raise ValueError("An approved traceability proposal is required")
    product, batch = trace["product"], trace["batch"]
    shipments = ledger.read("get_batch_shipments", batch_id=batch["id"])
    distribution = ledger.read("get_distribution_summary", batch_id=batch["id"])
    findings = ledger.read("get_inspection_findings", case_id=ledger.case_id)
    evidence = ledger.read("get_case_evidence_metadata", case_id=ledger.case_id)
    timeline = ledger.read("get_case_timeline", case_id=ledger.case_id)
    completed = [row for row in findings if row["status"] == "completed"]
    pending = [row for row in findings if row["status"] != "completed"]
    # Every recorded recipient must provide a human finding before escalation.
    expected = {row["retailer_id"] for row in shipments}
    if not expected or expected - {row["retailer_id"] for row in completed}:
        raise ValueError("All assigned supermarkets must submit human findings first")
    if decision.recommendation == "request_more_retailer_checks":
        if (
            not decision.followup_retailer_ids
            or not set(decision.followup_retailer_ids) <= expected
        ):
            raise ValueError("Choose followup_retailer_ids from the verified shipment recipients")
    outcomes = {row["finding"] for row in completed}
    conflicts = completed if {"issue_observed", "no_issue_observed"} <= outcomes else []
    packet = {
        "case_public_id": case["public_id"],
        "product": product,
        "batch": batch,
        "distribution": shipments,
        "distribution_summary": distribution,
        "findings": completed,
        "evidence": evidence,
        "timeline": timeline,
        "agent_summary": {
            "summary": decision.summary,
            "recommendation": decision.recommendation,
            "completed_inspections": len(completed),
            "pending_inspections": len(pending),
            "conflicting_findings": bool(conflicts),
        },
        "requested_actions": decision.manufacturer_questions,
    }
    return EscalationResult(
        type={
            "prepare_manufacturer_escalation": "manufacturer_escalation_packet",
            "request_more_retailer_checks": "retailer_followup",
            "continue_monitoring": "monitoring",
        }[decision.recommendation],
        followup_retailer_ids=decision.followup_retailer_ids,
        case_id=ledger.case_id,
        batch_id=batch["id"],
        completed_inspections=len(completed),
        pending_inspections=len(pending),
        findings_summary=completed,
        conflicting_findings=conflicts,
        affected_quantity=distribution["quantity_shipped"],
        checked_quantity=None,
        missing_evidence=[f"retailer_finding:{row['retailer_id']}" for row in pending],
        manufacturer_questions=decision.manufacturer_questions,
        recommendation=decision.recommendation,
        manufacturer_id=product["manufacturer"]["id"],
        manufacturer_packet=packet,
        rationale=decision.rationale,
        evidence_references=[
            ledger.case_id,
            batch["id"],
            *[row["inspection_id"] for row in completed],
            *[row["id"] for row in evidence],
        ],
        ai_assessment=assessment(decision),
    ).model_dump()


STAGES = {
    "triage": (
        TriageDecision,
        finalize_triage,
        "Investigate product candidates, missing information and related complaints. Choose "
        "catalogue "
        "search terms from the report; retry shorter useful terms if necessary. Select a candidate "
        "only when supported. If product and lot are known, read related reports. Recommend "
        "requesting "
        "information, retailer review, or importer investigation. An officer-forwarded photo case "
        "already has a verified identity; assess it for importer investigation. "
        "Assess intake readiness for tracing; batch safety is decided later. "
        "Request information only for a concrete intake blocker: an unresolved product, unreadable "
        "lot, unknown purchase supermarket, or a report too unclear to investigate. "
        "Missing lab confirmation, storage records, inspection findings, receipts, "
        "or related complaints do not by themselves block tracing an identified product and lot. "
        "Record those as follow-up questions for the downstream investigation. When the officer "
        "has forwarded a clearly described complaint with a resolved product, lot and supermarket, "
        "recommend importer investigation unless a specific intake contradiction blocks it. "
        "Explain any intake blocker precisely; do not ask generic questions as prerequisites.",
    ),
    "traceability": (
        TraceDecision,
        finalize_trace,
        "Investigate which catalogue product and exact lot match the case. Choose search terms and "
        "follow-up tool calls based on results. Resolve the batch with get_batch. Before proposing "
        "retailer checks, read shipments, excluded retailers and related reports for the exact "
        "product "
        "and lot. If unresolved, request information with useful questions. Explain match "
        "uncertainty. Your task is shipment tracing, not confirming contamination. "
        "When product, lot and shipment recipients are resolved, propose retailer_inspections "
        "so humans can investigate. Lab confirmation, recall status, storage history, and other "
        "retailer findings are downstream questions, not prerequisites for retailer checks. "
        "Use request_information only for a concrete missing or contradictory traceability fact "
        "and name it in missing. No related reports is a valid empty result, not a blocker.",
    ),
    "escalation": (
        EscalationDecision,
        finalize_escalation,
        "Read the approved trace, shipments, distribution summary, retailer findings, evidence "
        "metadata "
        "and timeline. Assess conflicts, pending checks and unanswered questions. Recommend "
        "manufacturer "
        "escalation, more checks, or monitoring. Prepare a concise summary and manufacturer "
        "questions. "
        "For more checks, select followup_retailer_ids from recorded shipment recipients. "
        "Every recommendation needs importer approval; only escalation sends a packet.",
    ),
}


async def run_groq_agent(agent_type, client, session, case_id):
    schema, finalize, instructions = STAGES[agent_type]
    return await run_tool_agent(
        agent_type, case_id, client, session, schema, instructions, finalize
    )
