"""Create the first importer account for a database without demo seeding."""

import getpass
import re

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Organization, User
from app.security import hash_password


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == "importer_investigator").limit(1)):
            raise SystemExit("An importer account already exists; no account was created.")

        code = input("Importer code: ").strip().upper()
        name = input("Importer organization name: ").strip()
        staff_name = input("Investigator name: ").strip()
        try:
            email = (
                TypeAdapter(EmailStr).validate_python(input("Investigator email: ").strip()).lower()
            )
        except ValidationError as exc:
            raise SystemExit("Enter a valid investigator email.") from exc
        password = getpass.getpass("Password (at least 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", code):
            raise SystemExit("Importer code must be 2–40 letters, numbers, _ or -.")
        if not name or not staff_name or len(name) > 200 or len(staff_name) > 120:
            raise SystemExit("Organization and investigator names are required.")
        if len(password) < 12 or not password.strip() or password != confirmation:
            raise SystemExit("Passwords must match and have at least 12 characters.")

        try:
            organization = Organization(code=code, name=name, type="importer")
            db.add(organization)
            db.flush()
            db.add(
                User(
                    email=email,
                    display_name=staff_name,
                    password_hash=hash_password(password),
                    role="importer_investigator",
                    organization_id=organization.id,
                )
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SystemExit(
                "Organization code or email already exists; no account was created."
            ) from exc
        print("Importer account created.")


if __name__ == "__main__":
    main()
