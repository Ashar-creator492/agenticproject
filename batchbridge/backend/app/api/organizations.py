from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import Organization, User
from app.schemas import OrganizationCreate, OrganizationView
from app.security import hash_password

router = APIRouter(prefix="/organizations", tags=["organizations"])
importer_only = require_roles("importer_investigator")


@router.get("", response_model=list[OrganizationView])
def list_organizations(_user: User = Depends(importer_only), db: Session = Depends(get_db)):
    return db.scalars(
        select(Organization)
        .where(Organization.type.in_(["retailer", "manufacturer"]))
        .order_by(Organization.type, Organization.name)
    ).all()


@router.post("", response_model=OrganizationView, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    _user: User = Depends(importer_only),
    db: Session = Depends(get_db),
):
    code = payload.code.strip().upper()
    email = str(payload.staff_email).lower()
    if (
        not payload.name.strip()
        or not payload.staff_name.strip()
        or not payload.staff_password.strip()
    ):
        raise HTTPException(status_code=422, detail="Names and password cannot be blank")
    if db.scalar(select(Organization.id).where(func.upper(Organization.code) == code)):
        raise HTTPException(status_code=409, detail="Organization code already exists")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="Staff email already exists")

    organization = Organization(code=code, name=payload.name.strip(), type=payload.type)
    try:
        db.add(organization)
        db.flush()
        db.add(
            User(
                email=email,
                display_name=payload.staff_name.strip(),
                password_hash=hash_password(payload.staff_password),
                role=(
                    "retailer_safety_manager"
                    if payload.type == "retailer"
                    else "manufacturer_reviewer"
                ),
                organization_id=organization.id,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Organization code or email already exists"
        ) from exc
    return organization
