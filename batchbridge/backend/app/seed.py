from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_audit
from app.config import get_settings
from app.models import (
    Batch,
    Case,
    Organization,
    Product,
    ProductAlias,
    RetailerReview,
    Shipment,
    User,
)
from app.security import hash_password, token_hash

DEMO_ORGANIZATIONS = [
    ("IMPORTER-PK", "Pak Continental Imports", "importer"),
    ("RETAILER-A", "CityMart Islamabad", "retailer"),
    ("RETAILER-B", "FreshBasket Rawalpindi", "retailer"),
    ("RETAILER-C", "Family Grocer Lahore", "retailer"),
    ("RETAILER-D", "Value Market Karachi", "retailer"),
    ("SWEETCO-DE", "SweetCo GmbH", "manufacturer"),
]

DEMO_COMPLAINTS = [
    (
        "ESC-DEMO-001",
        "Amina Yusuf",
        "RETAILER-A",
        date(2026, 10, 11),
        "White powdery marks appeared on two sealed chocolate bars from lot 38.",
    ),
    (
        "ESC-DEMO-002",
        "Omar Farooq",
        "RETAILER-B",
        date(2026, 10, 12),
        "The chocolate had an unusual sour smell immediately after opening the wrapper.",
    ),
    (
        "ESC-DEMO-003",
        "Sara Khan",
        "RETAILER-C",
        date(2026, 10, 12),
        "The inner foil was torn even though the outside package looked sealed.",
    ),
    (
        "ESC-DEMO-004",
        "Bilal Ahmed",
        "RETAILER-A",
        date(2026, 10, 13),
        "A chocolate bar from lot 38 tasted unusually bitter and was not consumed further.",
    ),
    (
        "ESC-DEMO-005",
        "Hina Malik",
        "RETAILER-B",
        date(2026, 10, 13),
        "The wrapper looked swollen and released air when the package was opened.",
    ),
    (
        "ESC-DEMO-006",
        "Zain Ali",
        "RETAILER-C",
        date(2026, 10, 14),
        "Grey discoloration was visible across several squares of the chocolate bar.",
    ),
    (
        "ESC-DEMO-007",
        "Mariam Noor",
        "RETAILER-A",
        date(2026, 10, 14),
        "The bar appeared melted and hardened again despite normal home storage.",
    ),
    (
        "ESC-DEMO-008",
        "Danish Iqbal",
        "RETAILER-B",
        date(2026, 10, 15),
        "Small dark particles were visible on the surface after opening the sealed pack.",
    ),
]


def seed_demo_complaints(db: Session) -> int:
    """Add stable fictional complaints without duplicating them on restart."""
    organizations = {
        organization.code: organization
        for organization in db.scalars(select(Organization)).all()
    }
    reviewers = {
        user.organization_id: user
        for user in db.scalars(
            select(User).where(User.role == "retailer_safety_manager")
        ).all()
    }
    demo_retailers = {row[2] for row in DEMO_COMPLAINTS}
    if not demo_retailers.issubset(organizations) or not all(
        organizations[code].id in reviewers for code in demo_retailers
    ):
        return 0

    inserted = 0
    for index, (public_id, reporter_name, retailer_code, purchase_date, description) in enumerate(
        DEMO_COMPLAINTS,
        start=1,
    ):
        if db.scalar(select(Case.id).where(Case.public_id == public_id)):
            continue
        retailer = organizations[retailer_code]
        reviewer = reviewers[retailer.id]
        created_at = datetime(2026, 10, 16, 9, index, tzinfo=timezone.utc)
        case = Case(
            public_id=public_id,
            tracking_token_hash=token_hash(f"batchbridge-demo-complaint-{index}"),
            source="customer",
            reporter_name=reporter_name,
            retailer_id=retailer.id,
            product_name="SweetCo Alpine Milk Chocolate 100g",
            batch_number="38",
            purchase_date=purchase_date,
            description=description,
            status="under_review",
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(case)
        db.flush()
        db.add(
            RetailerReview(
                case_id=case.id,
                retailer_id=retailer.id,
                reviewer_id=reviewer.id,
                decision="forwarded",
                notes="Fictional demo complaint verified and forwarded for importer investigation.",
                created_at=created_at,
            )
        )
        add_audit(db, case.id, "report_created", details={"source": "customer", "demo": True})
        add_audit(
            db,
            case.id,
            "retailer_review_submitted",
            reviewer.id,
            {"decision": "forwarded", "demo": True},
        )
        inserted += 1
    return inserted


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(Organization.id).limit(1)):
        email_renames = {
            "importer@batchbridge.demo": "importer@escalera.demo",
            "retailer-a@batchbridge.demo": "retailer-a@escalera.demo",
            "retailer-b@batchbridge.demo": "retailer-b@escalera.demo",
            "retailer-c@batchbridge.demo": "retailer-c@escalera.demo",
            "manufacturer@batchbridge.demo": "manufacturer@escalera.demo",
        }
        for old_email, new_email in email_renames.items():
            user = db.scalar(select(User).where(User.email == old_email))
            if user and not db.scalar(select(User.id).where(User.email == new_email)):
                user.email = new_email
        for case in db.scalars(select(Case).where(Case.public_id.startswith("BB-"))).all():
            case.public_id = case.public_id.replace("BB-", "ESC-", 1)
        db.flush()
        seed_demo_complaints(db)
        db.commit()
        return

    organizations: dict[str, Organization] = {}
    for code, name, org_type in DEMO_ORGANIZATIONS:
        org = Organization(code=code, name=name, type=org_type)
        db.add(org)
        organizations[code] = org
    db.flush()

    password_hash = hash_password(get_settings().demo_password)
    users = [
        ("importer@escalera.demo", "Ayesha Khan", "importer_investigator", "IMPORTER-PK"),
        ("retailer-a@escalera.demo", "Ali Raza", "retailer_safety_manager", "RETAILER-A"),
        ("retailer-b@escalera.demo", "Sara Ahmed", "retailer_safety_manager", "RETAILER-B"),
        ("retailer-c@escalera.demo", "Hamza Malik", "retailer_safety_manager", "RETAILER-C"),
        ("manufacturer@escalera.demo", "Lea Fischer", "manufacturer_reviewer", "SWEETCO-DE"),
    ]
    for email, name, role, org_code in users:
        db.add(
            User(
                email=email,
                display_name=name,
                password_hash=password_hash,
                role=role,
                organization_id=organizations[org_code].id,
            )
        )

    product = Product(
        sku="CHOC-100",
        name="SweetCo Alpine Milk Chocolate 100g",
        manufacturer_id=organizations["SWEETCO-DE"].id,
    )
    db.add(product)
    db.flush()
    for alias in ["Sweet Co Milk Chocolate", "Alpine Chocolate", "SweetCo Choco Bar"]:
        db.add(ProductAlias(product_id=product.id, alias=alias))

    batch_38 = Batch(
        product_id=product.id,
        batch_number="38",
        quantity_received=10_000,
        expiry_date=date(2027, 8, 31),
    )
    batch_39 = Batch(
        product_id=product.id,
        batch_number="39",
        quantity_received=2_000,
        expiry_date=date(2027, 9, 30),
    )
    db.add_all([batch_38, batch_39])
    db.flush()

    shipped_at = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    for reference, batch, retailer_code, quantity in [
        ("SHIP-38-A", batch_38, "RETAILER-A", 3_000),
        ("SHIP-38-B", batch_38, "RETAILER-B", 2_000),
        ("SHIP-38-C", batch_38, "RETAILER-C", 1_000),
        ("SHIP-39-D", batch_39, "RETAILER-D", 1_000),
    ]:
        db.add(
            Shipment(
                shipment_reference=reference,
                batch_id=batch.id,
                retailer_id=organizations[retailer_code].id,
                quantity=quantity,
                shipped_at=shipped_at,
            )
        )
    seed_demo_complaints(db)
    db.commit()
