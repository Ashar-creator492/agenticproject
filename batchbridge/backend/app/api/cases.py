import asyncio
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.audit import add_audit
from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import (
    AgentRun,
    Approval,
    AuditEvent,
    Case,
    Escalation,
    Evidence,
    Inspection,
    Organization,
    Proposal,
    RetailerReview,
    User,
)
from app.schemas import (
    AnalysisStartResponse,
    ApprovalRequest,
    CaseInformationCreate,
    CaseSummary,
    DemoBarcodeRequest,
    OfficerReportCreate,
    RetailerReviewRequest,
    StatusUpdate,
)
from app.security import token_hash
from app.services.case_workflow import proposal_block_reason, stage_block_reason, workflow_view
from app.services.demo_barcodes import resolve_demo_barcode
from app.services.investigation import (
    execute_investigation,
    queue_investigation,
    resume_investigation,
)

router = APIRouter(prefix="/cases", tags=["cases"])


def _can_view_case(db: Session, user: User, case: Case) -> bool:
    if user.role == "importer_investigator":
        return True
    if user.role == "retailer_safety_manager":
        return case.retailer_id == user.organization_id or bool(
            db.scalar(
                select(
                    exists().where(
                        Inspection.case_id == case.id,
                        Inspection.retailer_id == user.organization_id,
                    )
                )
            )
        )
    return False


def _get_authorized_case(db: Session, user: User, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if not case or not _can_view_case(db, user, case):
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("", response_model=list[CaseSummary])
def list_cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Case).order_by(Case.created_at.desc())
    if user.role == "retailer_safety_manager":
        assigned_case_ids = select(Inspection.case_id).where(
            Inspection.retailer_id == user.organization_id
        )
        query = query.where(
            (Case.retailer_id == user.organization_id) | Case.id.in_(assigned_case_ids)
        )
    elif user.role != "importer_investigator":
        raise HTTPException(status_code=403, detail="Role not permitted")
    return db.scalars(query).all()


@router.post("/officer-report", response_model=CaseSummary, status_code=status.HTTP_201_CREATED)
def create_officer_report(
    payload: OfficerReportCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles("retailer_safety_manager")),
    db: Session = Depends(get_db),
):
    raw_tracking = secrets.token_urlsafe(24)
    case = Case(
        public_id=f"ESC-{secrets.token_hex(5).upper()}",
        tracking_token_hash=token_hash(raw_tracking),
        source="retailer_officer",
        retailer_id=user.organization_id,
        product_name=payload.product_name.strip(),
        batch_number=payload.batch_number.strip() if payload.batch_number else None,
        purchase_date=payload.purchase_date,
        description=payload.description.strip(),
        created_by_user_id=user.id,
    )
    db.add(case)
    db.flush()
    add_audit(db, case.id, "report_created", user.id, {"source": "retailer_officer"})
    run, _ = queue_investigation(db, case.id, "triage", user.id)
    db.commit()
    background_tasks.add_task(execute_investigation, run.id)
    return case


@router.get("/{case_id}")
def case_detail(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = _get_authorized_case(db, user, case_id)
    proposals = db.scalars(
        select(Proposal).where(Proposal.case_id == case.id).order_by(Proposal.version.desc())
    ).all()
    inspections = db.scalars(
        select(Inspection).where(Inspection.case_id == case.id).order_by(Inspection.created_at)
    ).all()
    timeline = db.scalars(
        select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at)
    ).all()
    agent_runs = db.scalars(
        select(AgentRun).where(AgentRun.case_id == case.id).order_by(AgentRun.created_at)
    ).all()
    evidence = db.scalars(
        select(Evidence).where(Evidence.case_id == case.id).order_by(Evidence.created_at)
    ).all()
    retailer_review = db.scalar(select(RetailerReview).where(RetailerReview.case_id == case.id))
    result = {
        "case": CaseSummary.model_validate(case).model_dump(mode="json"),
        "description": case.description,
        "workflow": workflow_view(db, case),
        "manufacturer_response": (
            escalation.response
            if (escalation := db.scalar(select(Escalation).where(Escalation.case_id == case.id)))
            else None
        ),
        "purchase_date": case.purchase_date,
        "evidence": [
            {
                "id": item.id,
                "filename": item.filename,
                "content_type": item.content_type,
                "url": f"/api/v1/evidence/{item.id}",
            }
            for item in evidence
        ],
        "retailer_review": (
            {"decision": retailer_review.decision, "notes": retailer_review.notes}
            if retailer_review
            else None
        ),
        "demo_verification": next(
            (
                event.details
                for event in reversed(timeline)
                if event.event_type == "demo_barcode_verified"
            ),
            None,
        ),
        "proposals": [
            {
                "id": item.id,
                "type": item.type,
                "payload": item.payload,
                "status": item.status,
                "version": item.version,
                "review_block_reason": proposal_block_reason(db, case, item)
                if item.status == "pending"
                else None,
                "created_at": item.created_at,
            }
            for item in proposals
        ],
        "inspections": [
            {
                "id": item.id,
                "retailer_id": item.retailer_id,
                "retailer_name": db.get(Organization, item.retailer_id).name,
                "status": item.status,
                "finding": item.finding,
                "notes": item.notes,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
            }
            for item in inspections
        ],
        "timeline": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "actor_user_id": item.actor_user_id,
                "details": item.details,
                "created_at": item.created_at,
            }
            for item in timeline
        ],
        "agent_runs": [
            {
                "id": item.id,
                "agent_type": item.agent_type,
                "status": item.status,
                "result": item.result,
                "error": item.error,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
            }
            for item in agent_runs
        ],
    }
    # Reporter contact details stay outside agent and manufacturer views.
    if user.role == "importer_investigator":
        result["reporter"] = {"name": case.reporter_name, "email": case.reporter_email}
    return result


@router.post("/{case_id}/demo-barcode")
def lookup_demo_barcode(
    case_id: str,
    payload: DemoBarcodeRequest,
    user: User = Depends(require_roles("retailer_safety_manager")),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case or case.retailer_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return resolve_demo_barcode(db, payload.barcode, user.organization_id)


@router.post("/{case_id}/retailer-review")
def review_customer_case(
    case_id: str,
    payload: RetailerReviewRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles("retailer_safety_manager")),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case or case.retailer_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Case not found")
    existing = db.scalar(
        select(RetailerReview).where(
            RetailerReview.case_id == case.id,
            RetailerReview.retailer_id == user.organization_id,
        )
    )
    if existing and (existing.decision == "forwarded" or existing.decision == payload.decision):
        return {
            "id": existing.id,
            "decision": existing.decision,
            "idempotent": True,
        }
    if payload.decision == "forwarded" and case.source == "customer_photo":
        if not payload.demo_barcode:
            raise HTTPException(status_code=409, detail="Verify a demo barcode before forwarding")
        match = resolve_demo_barcode(db, payload.demo_barcode, user.organization_id)
        case.product_name = match["product_name"]
        case.batch_number = match["batch_number"]
        add_audit(db, case.id, "demo_barcode_verified", user.id, match)
    review = existing
    if not review:
        review = RetailerReview(
            case_id=case.id,
            retailer_id=user.organization_id,
            reviewer_id=user.id,
            decision=payload.decision,
            notes=payload.notes,
        )
        db.add(review)
    else:
        review.decision = payload.decision
        review.notes = payload.notes
        review.reviewer_id = user.id
    if payload.decision == "forwarded":
        case.status = "under_review"
    elif payload.decision == "needs_customer_information":
        case.status = "waiting_for_information"
    db.flush()
    add_audit(
        db,
        case.id,
        "retailer_review_submitted",
        user.id,
        {
            "review_id": review.id,
            "decision": review.decision,
            "notes": review.notes,
            "forwarded_to_importer": review.decision == "forwarded",
        },
    )
    if payload.decision == "forwarded" and case.source == "customer_photo":
        run, created = queue_investigation(db, case.id, "triage", user.id)
        if created:
            background_tasks.add_task(execute_investigation, run.id)
    db.commit()
    return {"id": review.id, "decision": review.decision, "idempotent": False}


@router.post("/{case_id}/information")
def add_case_information(
    case_id: str,
    payload: CaseInformationCreate,
    user: User = Depends(require_roles("importer_investigator")),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    if case.status == "closed":
        raise HTTPException(status_code=409, detail="This case is closed")
    identity_changed = (
        payload.product_name is not None and payload.product_name != case.product_name
    ) or (payload.batch_number is not None and payload.batch_number != case.batch_number)
    if identity_changed and db.scalar(select(Inspection.id).where(Inspection.case_id == case.id)):
        raise HTTPException(
            status_code=409,
            detail="Identity cannot change after retailer checks are assigned. Create a new case.",
        )
    if payload.product_name:
        case.product_name = payload.product_name.strip()
    if payload.batch_number:
        case.batch_number = payload.batch_number.strip()
    case.description += "\nAdditional information: " + payload.notes.strip()
    add_audit(db, case.id, "case_information_added", user.id, payload.model_dump(exclude_none=True))
    db.commit()
    return {
        "case_id": case.id,
        "message": "Information saved. Rerun triage and review the new proposal.",
    }


@router.patch("/{case_id}/status", response_model=CaseSummary)
def update_case_status(
    case_id: str,
    payload: StatusUpdate,
    user: User = Depends(require_roles("importer_investigator")),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    if case.status == "closed":
        raise HTTPException(status_code=409, detail="This case is closed")
    if payload.status in {"retailer_checks", "manufacturer_review"}:
        raise HTTPException(status_code=409, detail="This status requires an approved agent action")
    if payload.status == "closed" or payload.safety_verdict:
        response = db.scalar(
            select(Escalation).where(
                Escalation.case_id == case.id, Escalation.status == "responded"
            )
        )
        if not response or not payload.notes or not payload.notes.strip():
            raise HTTPException(
                status_code=409,
                detail="Manufacturer response and notes are required for a final verdict",
            )
    old_status = case.status
    case.status = payload.status
    if payload.safety_verdict:
        case.safety_verdict = payload.safety_verdict
    add_audit(
        db,
        case.id,
        "case_status_changed",
        user.id,
        {
            "from": old_status,
            "to": case.status,
            "safety_verdict": case.safety_verdict,
            "notes": payload.notes,
        },
    )
    db.commit()
    return case


async def _start_agent(
    db: Session,
    case: Case,
    agent_type: str,
    user: User,
) -> AnalysisStartResponse:
    reason = stage_block_reason(db, case, agent_type)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    run, created = queue_investigation(db, case.id, agent_type, user.id)
    if agent_type == "traceability":
        case.status = "under_review"
    db.commit()
    if created:
        asyncio.create_task(execute_investigation(run.id))
    return AnalysisStartResponse(run_id=run.id, status=run.status, agent_type=agent_type)


@router.post("/{case_id}/triage", response_model=AnalysisStartResponse, status_code=202)
async def start_triage(
    case_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    if user.role not in {"retailer_safety_manager", "importer_investigator"}:
        raise HTTPException(status_code=403, detail="Role not permitted")
    return await _start_agent(db, case, "triage", user)


@router.post("/{case_id}/analysis", response_model=AnalysisStartResponse, status_code=202)
async def start_analysis(
    case_id: str,
    user: User = Depends(require_roles("importer_investigator")),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    return await _start_agent(db, case, "traceability", user)


@router.post(
    "/{case_id}/escalation-analysis", response_model=AnalysisStartResponse, status_code=202
)
async def start_escalation_analysis(
    case_id: str,
    user: User = Depends(require_roles("importer_investigator")),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    return await _start_agent(db, case, "escalation", user)


@router.get("/{case_id}/analysis/{run_id}")
def get_analysis(
    case_id: str,
    run_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    run = db.get(AgentRun, run_id)
    if not run or run.case_id != case.id:
        raise HTTPException(status_code=404, detail="Run not found")
    proposal = db.scalar(select(Proposal).where(Proposal.agent_run_id == run.id))
    return {
        "id": run.id,
        "agent_type": run.agent_type,
        "status": run.status,
        "result": run.result,
        "error": run.error,
        "proposal_id": proposal.id if proposal else None,
    }


@router.post("/{case_id}/approvals")
async def decide_proposal(
    case_id: str,
    payload: ApprovalRequest,
    user: User = Depends(require_roles("importer_investigator")),
    db: Session = Depends(get_db),
):
    case = _get_authorized_case(db, user, case_id)
    proposal = db.get(Proposal, payload.proposal_id)
    if not proposal or proposal.case_id != case.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    existing = db.scalar(select(Approval).where(Approval.proposal_id == proposal.id))
    if existing:
        if existing.decision != payload.decision:
            raise HTTPException(
                status_code=409,
                detail="This decision is already recorded. Rerun the agent for a new proposal.",
            )
        return {"approval_id": existing.id, "decision": existing.decision, "idempotent": True}
    reason = proposal_block_reason(db, case, proposal)
    if reason:
        raise HTTPException(status_code=409, detail=reason)

    approval = Approval(
        proposal_id=proposal.id,
        reviewer_id=user.id,
        decision=payload.decision,
        notes=payload.notes,
    )
    db.add(approval)
    proposal.status = payload.decision
    if payload.decision == "approved" and proposal.type == "retailer_inspections":
        for shipment in proposal.payload.get("retailers", []):
            retailer_id = shipment["retailer_id"]
            exists_already = db.scalar(
                select(Inspection.id).where(
                    Inspection.case_id == case.id,
                    Inspection.retailer_id == retailer_id,
                )
            )
            if not exists_already:
                db.add(
                    Inspection(
                        case_id=case.id,
                        retailer_id=retailer_id,
                        assigned_by_user_id=user.id,
                    )
                )
        case.status = "retailer_checks"
    elif payload.decision == "approved" and proposal.type == "request_information":
        case.status = "waiting_for_information"
    elif payload.decision == "approved" and proposal.type == "triage_recommendation":
        recommendation = proposal.payload["recommendation"]
        case.status = (
            "waiting_for_information" if recommendation == "request_information" else "under_review"
        )
    elif payload.decision == "approved" and proposal.type == "retailer_followup":
        targets = set(proposal.payload.get("followup_retailer_ids", []))
        checks = db.scalars(select(Inspection).where(Inspection.case_id == case.id)).all()
        if not targets or not targets <= {row.retailer_id for row in checks}:
            raise HTTPException(
                status_code=409, detail="Follow-up targets must be assigned supermarkets"
            )
        for check in checks:
            if check.retailer_id in targets:
                add_audit(
                    db,
                    case.id,
                    "retailer_check_reopened",
                    user.id,
                    {
                        "inspection_id": check.id,
                        "previous_finding": check.finding,
                        "previous_notes": check.notes,
                    },
                )
                check.status = "pending"
                check.finding = None
                check.notes = None
                check.completed_at = None
                check.reviewed_by_user_id = None
        case.status = "retailer_checks"
    elif payload.decision == "approved" and proposal.type == "manufacturer_escalation_packet":
        existing_escalation = db.scalar(select(Escalation).where(Escalation.case_id == case.id))
        if existing_escalation:
            raise HTTPException(
                status_code=409, detail="A manufacturer packet was already sent for this case"
            )
        if not existing_escalation:
            packet = dict(proposal.payload["manufacturer_packet"])
            if payload.notes:
                packet["importer_notes"] = payload.notes
            escalation = Escalation(
                case_id=case.id,
                manufacturer_id=proposal.payload["manufacturer_id"],
                packet=packet,
                approved_by_user_id=user.id,
            )
            db.add(escalation)
            db.flush()
            add_audit(
                db,
                case.id,
                "manufacturer_escalation_sent",
                user.id,
                {
                    "escalation_id": escalation.id,
                    "manufacturer_id": escalation.manufacturer_id,
                    "proposal_id": proposal.id,
                },
            )
        case.status = "manufacturer_review"
    else:
        case.status = "under_review"
    add_audit(
        db,
        case.id,
        "proposal_reviewed",
        user.id,
        {"proposal_id": proposal.id, "decision": payload.decision, "notes": payload.notes},
    )
    run = db.get(AgentRun, proposal.agent_run_id)
    run.status = "completed"
    db.commit()
    await resume_investigation(run.thread_id, payload.decision, payload.notes)
    return {"approval_id": approval.id, "decision": approval.decision, "idempotent": False}
