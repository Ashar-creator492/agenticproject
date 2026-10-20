from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import agent_execution_mode
from app.models import (
    AgentRun,
    Approval,
    AuditEvent,
    Batch,
    Case,
    Inspection,
    Proposal,
    RetailerReview,
    Shipment,
)

STAGES = ("triage", "traceability", "escalation")


def latest_stage(db: Session, case_id: str, stage: str):
    run = db.scalar(
        select(AgentRun)
        .where(
            AgentRun.case_id == case_id,
            AgentRun.agent_type == stage,
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(1)
    )
    proposal = db.scalar(select(Proposal).where(Proposal.agent_run_id == run.id)) if run else None
    return run, proposal


def _revision(db: Session, case_id: str, events: list[str]):
    return db.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.case_id == case_id,
            AuditEvent.event_type.in_(events),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )


def input_snapshot(db: Session, case: Case, stage: str) -> dict:
    # Approved proposals become stale whenever their supporting facts change.
    snapshot = {
        "version": 1,
        "identity": [case.product_name, case.batch_number, case.retailer_id],
        "information_revision": _revision(db, case.id, ["case_information_added"]),
    }
    if stage != "triage":
        _, triage = latest_stage(db, case.id, "triage")
        snapshot["triage_proposal_id"] = triage.id if triage else None
    if stage == "escalation":
        _, trace = latest_stage(db, case.id, "traceability")
        snapshot["traceability_proposal_id"] = trace.id if trace else None
        snapshot["evidence_revision"] = _revision(
            db,
            case.id,
            [
                "evidence_added",
                "retailer_finding_submitted",
                "retailer_check_reopened",
            ],
        )
    return snapshot


def approved_latest(db: Session, case: Case, stage: str):
    run, proposal = latest_stage(db, case.id, stage)
    if not run or not proposal or proposal.status != "approved":
        return None
    if run.input_snapshot != input_snapshot(db, case, stage):
        return None
    if not db.scalar(
        select(Approval.id).where(
            Approval.proposal_id == proposal.id,
            Approval.decision == "approved",
        )
    ):
        return None
    return proposal


def shipment_plan_current(db: Session, case: Case, proposal: Proposal) -> bool:
    payload = proposal.payload
    batch = db.get(Batch, payload.get("matched_batch_id"))
    if not batch or batch.batch_number != case.batch_number:
        return False
    if batch.product_id != payload.get("matched_product_id"):
        return False
    # Require an exact match so outdated recipient lists cannot be approved.
    actual = {
        (row.id, row.retailer_id, row.quantity)
        for row in db.scalars(select(Shipment).where(Shipment.batch_id == batch.id)).all()
    }
    proposed = {
        (row.get("shipment_id"), row.get("retailer_id"), row.get("quantity"))
        for row in payload.get("retailers", [])
    }
    return bool(actual) and actual == proposed


def stage_block_reason(db: Session, case: Case, stage: str) -> str | None:
    if case.status == "closed":
        return "This case is closed."
    other_running = db.scalar(
        select(AgentRun).where(
            AgentRun.case_id == case.id,
            AgentRun.agent_type != stage,
            AgentRun.status.in_(["queued", "running"]),
        )
    )
    if other_running:
        return f"Wait for the {other_running.agent_type} agent to finish."
    if stage == "triage":
        return None
    triage = approved_latest(db, case, "triage")
    if not triage:
        triage_run, triage_proposal = latest_stage(db, case.id, "triage")
        if triage_run and triage_proposal and triage_proposal.status == "approved":
            if triage_run.input_snapshot != input_snapshot(db, case, "triage"):
                return (
                    "Case information changed after triage. Run Triage Agent again, "
                    "approve its new proposal, then run Traceability Agent."
                )
        return "Run triage and explicitly approve its latest proposal before traceability."
    if triage.payload.get("recommendation") == "request_information":
        return "Triage requested information. Add the missing details, rerun triage and review it."
    forwarded = db.scalar(
        select(RetailerReview.id).where(
            RetailerReview.case_id == case.id,
            RetailerReview.decision == "forwarded",
        )
    )
    if (
        case.source == "customer_photo" or triage.payload.get("recommendation") == "retailer_review"
    ) and not forwarded:
        return "The supermarket officer must verify and forward this complaint."
    if stage == "traceability":
        return None
    trace = approved_latest(db, case, "traceability")
    if not trace or trace.type != "retailer_inspections":
        return "Run traceability and approve its latest retailer-check proposal."
    if not shipment_plan_current(db, case, trace):
        return "Shipment records changed. Rerun traceability and review the updated recipients."
    expected = {row["retailer_id"] for row in trace.payload["retailers"]}
    checks = db.scalars(select(Inspection).where(Inspection.case_id == case.id)).all()
    completed = {row.retailer_id for row in checks if row.status == "completed"}
    outstanding = expected - completed
    if outstanding:
        return f"Waiting for {len(outstanding)} of {len(expected)} supermarkets to submit findings."
    return None


def proposal_block_reason(db: Session, case: Case, proposal: Proposal) -> str | None:
    run = db.get(AgentRun, proposal.agent_run_id)
    latest, _ = latest_stage(db, case.id, run.agent_type)
    if not latest or run.id != latest.id:
        return "A newer agent run exists. Review the latest proposal."
    if run.input_snapshot != input_snapshot(db, case, run.agent_type):
        return "This proposal uses older inputs or approvals. Rerun the agent before approving it."
    if (run.result or {}).get("execution_mode") != agent_execution_mode(run.agent_type):
        return "Execution mode changed. Rerun this stage to review its current proposal."
    if run.status != "awaiting_human" or proposal.status != "pending":
        return "This proposal is no longer awaiting review."
    reason = stage_block_reason(db, case, run.agent_type)
    if reason:
        return reason
    if proposal.type == "retailer_inspections" and not shipment_plan_current(db, case, proposal):
        return "Shipment records changed. Rerun traceability before assigning checks."
    if (
        proposal.type == "manufacturer_escalation_packet"
        and proposal.payload.get("recommendation") != "prepare_manufacturer_escalation"
    ):
        return "The recommendation is more checks or monitoring. Rerun escalation."
    return None


def workflow_view(db: Session, case: Case) -> dict:
    steps = {}
    for stage in STAGES:
        run, proposal = latest_stage(db, case.id, stage)
        reason = stage_block_reason(db, case, stage)
        running = run and run.status in {"queued", "running"}
        if not reason and run and run.status == "awaiting_human" and proposal:
            if not proposal_block_reason(db, case, proposal):
                reason = f"Review the pending {stage} proposal before running it again."
        steps[stage] = {
            "can_run": not reason and not running,
            "blocked_reason": reason or ("Agent is running." if running else None),
            "latest_proposal_id": proposal.id if proposal else None,
        }
    return steps
