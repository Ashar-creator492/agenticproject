from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


def add_audit(
    db: Session,
    case_id: str,
    event_type: str,
    actor_user_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    # The caller commits this event with the workflow change it describes.
    db.add(
        AuditEvent(
            case_id=case_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            details=details or {},
        )
    )
