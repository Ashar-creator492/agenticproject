import io
import time

import pytest
from app import bootstrap_importer
from app.database import Base, make_engine
from app.models import Organization, User
from app.security import verify_password
from app.seed import seed_demo_complaints
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _organization(code: str, kind: str, email: str) -> dict:
    return {
        "code": code,
        "name": f"Test {kind} {code}",
        "type": kind,
        "staff_name": "Test Reviewer",
        "staff_email": email,
        "staff_password": "new-staff-password-2026",
    }


def test_importer_can_create_organizations_and_import_their_records(client, login_user):
    assert client.get("/api/v1/organizations").status_code == 401
    login_user(client, "importer@escalera.demo")

    manufacturer = _organization("maker-new", "manufacturer", "maker-new@example.com")
    retailer = _organization("retailer-new", "retailer", "retailer-new@example.com")
    for payload in (manufacturer, retailer):
        response = client.post("/api/v1/organizations", json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["code"] == payload["code"].upper()
        assert "staff_password" not in response.json()

    organizations = client.get("/api/v1/organizations")
    assert organizations.status_code == 200
    assert {item["code"] for item in organizations.json()} >= {"MAKER-NEW", "RETAILER-NEW"}

    batches = (
        "sku,product_name,manufacturer_code,batch_number,quantity_received,expiry_date\n"
        "NEW-FOOD,New Food Bar,MAKER-NEW,L-2026,120,2027-12-31\n"
    )
    response = client.post(
        "/api/v1/imports/batches",
        files={"file": ("batches.csv", io.BytesIO(batches.encode()), "text/csv")},
    )
    assert response.json() == {"inserted": 1, "skipped": 0, "errors": []}

    shipments = (
        "shipment_reference,sku,batch_number,retailer_code,quantity,shipped_at\n"
        "SHIP-NEW-1,NEW-FOOD,L-2026,RETAILER-NEW,40,2026-11-01T09:00:00Z\n"
    )
    response = client.post(
        "/api/v1/imports/shipments",
        files={"file": ("shipments.csv", io.BytesIO(shipments.encode()), "text/csv")},
    )
    assert response.json() == {"inserted": 1, "skipped": 0, "errors": []}
    assert any(item["sku"] == "NEW-FOOD" for item in client.get("/api/v1/catalog/batches").json())
    assert any(
        item["shipment_reference"] == "SHIP-NEW-1"
        for item in client.get("/api/v1/catalog/shipments").json()
    )

    client.post("/api/v1/auth/logout")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "retailer-new@example.com", "password": "new-staff-password-2026"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "retailer_safety_manager"
    assert client.get("/api/v1/organizations").status_code == 403
    assert client.post("/api/v1/organizations", json=retailer).status_code == 403

    report = client.post(
        "/api/v1/cases/officer-report",
        json={
            "product_name": "NEW-FOOD",
            "batch_number": "L-2026",
            "description": "The sealed food bar had a visible packaging defect.",
        },
    )
    assert report.status_code == 201, report.text
    case = report.json()

    client.post("/api/v1/auth/logout")
    login_user(client, "importer@escalera.demo")
    triage = client.get(f"/api/v1/cases/{case['id']}").json()["proposals"][0]
    assert (
        client.post(
            f"/api/v1/cases/{case['id']}/approvals",
            json={"proposal_id": triage["id"], "decision": "approved"},
        ).status_code
        == 200
    )
    start = client.post(f"/api/v1/cases/{case['id']}/analysis")
    assert start.status_code == 202, start.text
    for _ in range(100):
        trace = client.get(f"/api/v1/cases/{case['id']}/analysis/{start.json()['run_id']}").json()
        if trace["status"] in {"awaiting_human", "failed"}:
            break
        time.sleep(0.05)
    assert trace["status"] == "awaiting_human", trace
    assert trace["result"]["type"] == "retailer_inspections"
    assert [row["retailer_code"] for row in trace["result"]["retailers"]] == ["RETAILER-NEW"]
    assert (
        client.post(
            f"/api/v1/cases/{case['id']}/approvals",
            json={"proposal_id": trace["proposal_id"], "decision": "approved"},
        ).status_code
        == 200
    )

    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "retailer-new@example.com", "password": "new-staff-password-2026"},
        ).status_code
        == 200
    )
    task = next(
        item for item in client.get("/api/v1/inspections").json() if item["case_id"] == case["id"]
    )
    assert (
        client.post(
            f"/api/v1/inspections/{task['id']}/finding",
            json={"finding": "issue_observed", "notes": "Matching lot checked at this retailer."},
        ).status_code
        == 200
    )

    client.post("/api/v1/auth/logout")
    login_user(client, "importer@escalera.demo")
    start = client.post(f"/api/v1/cases/{case['id']}/escalation-analysis")
    assert start.status_code == 202, start.text
    for _ in range(100):
        escalation = client.get(
            f"/api/v1/cases/{case['id']}/analysis/{start.json()['run_id']}"
        ).json()
        if escalation["status"] in {"awaiting_human", "failed"}:
            break
        time.sleep(0.05)
    assert escalation["status"] == "awaiting_human", escalation
    assert escalation["result"]["type"] == "manufacturer_escalation_packet"
    assert (
        client.post(
            f"/api/v1/cases/{case['id']}/approvals",
            json={"proposal_id": escalation["proposal_id"], "decision": "approved"},
        ).status_code
        == 200
    )

    client.post("/api/v1/auth/logout")
    manufacturer_login = client.post(
        "/api/v1/auth/login",
        json={"email": "maker-new@example.com", "password": "new-staff-password-2026"},
    )
    assert manufacturer_login.status_code == 200
    inbox_item = next(
        item for item in client.get("/api/v1/escalations").json() if item["case_id"] == case["id"]
    )
    assert (
        client.post(
            f"/api/v1/escalations/{inbox_item['id']}/response",
            json={"response": "Manufacturer is reviewing the lot records."},
        ).status_code
        == 200
    )

    client.post("/api/v1/auth/logout")
    login_user(client, "importer@escalera.demo")
    assert (
        client.patch(
            f"/api/v1/cases/{case['id']}/status",
            json={
                "status": "closed",
                "safety_verdict": "unconfirmed",
                "notes": "Review completed.",
            },
        ).status_code
        == 200
    )


def test_organization_creation_rejects_duplicate_codes_and_emails(client, login_user):
    login_user(client, "importer@escalera.demo")
    duplicate_code = _organization("RETAILER-A", "retailer", "another@example.com")
    assert client.post("/api/v1/organizations", json=duplicate_code).status_code == 409
    duplicate_email = _organization("RETAILER-OTHER", "retailer", "RETAILER-A@ESCALERA.DEMO")
    assert client.post("/api/v1/organizations", json=duplicate_email).status_code == 409
    assert (
        client.post(
            "/api/v1/organizations",
            json=_organization("BAD", "retailer", "bad@example.com") | {"staff_password": "short"},
        ).status_code
        == 422
    )


def test_fresh_database_can_bootstrap_importer_without_demo_records(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(bootstrap_importer, "SessionLocal", sessionmaker(bind=engine))
    answers = iter(["importer-new", "New Importer", "New Investigator", "owner@example.com"])
    passwords = iter(["initial-password-2026", "initial-password-2026"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(bootstrap_importer.getpass, "getpass", lambda _prompt: next(passwords))

    bootstrap_importer.main()
    with sessionmaker(bind=engine)() as db:
        organization = db.scalar(select(Organization))
        user = db.scalar(select(User))
        assert organization.code == "IMPORTER-NEW"
        assert user.organization_id == organization.id
        assert user.role == "importer_investigator"
        assert verify_password("initial-password-2026", user.password_hash)
        assert db.query(Organization).count() == 1
        assert seed_demo_complaints(db) == 0

    with pytest.raises(SystemExit, match="already exists"):
        bootstrap_importer.main()
    engine.dispose()
