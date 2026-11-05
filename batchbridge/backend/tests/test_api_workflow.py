import csv
import io
import time


def _logout(client):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204


def test_complete_human_approved_batch_investigation(client, login_user):
    report = client.post(
        "/api/v1/reports",
        json={
            "reporter_name": "Demo Customer",
            "reporter_email": "customer@example.com",
            "retailer_code": "RETAILER-A",
            "product_name": "SweetCo Alpine Milk Chocolate 100g",
            "batch_number": "38",
            "purchase_date": "2026-10-15",
            "description": "The sealed chocolate had an unusual smell and visible discoloration.",
        },
    )
    assert report.status_code == 201, report.text
    tracking_token = report.json()["tracking_token"]
    evidence_content = b"fictional package photo bytes"
    evidence = client.post(
        f"/api/v1/reports/{report.json()['case_id']}/evidence",
        params={"tracking_token": tracking_token},
        files={"file": ("package.png", evidence_content, "image/png")},
    )
    assert evidence.status_code == 201, evidence.text

    tracked = client.get(f"/api/v1/tracking/{tracking_token}")
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "new_report"

    login_user(client, "retailer-a@escalera.demo")
    retailer_case = next(
        item
        for item in client.get("/api/v1/cases").json()
        if item["public_id"] == report.json()["case_id"]
    )
    triage_detail = client.get(f"/api/v1/cases/{retailer_case['id']}").json()
    triage_run = next(
        item for item in triage_detail["agent_runs"] if item["agent_type"] == "triage"
    )
    assert triage_run["status"] == "awaiting_human"
    assert triage_run["result"]["type"] == "triage_recommendation"
    assert triage_run["result"]["recommendation"] == "retailer_review"
    retailer_review = client.post(
        f"/api/v1/cases/{retailer_case['id']}/retailer-review",
        json={
            "decision": "forwarded",
            "notes": "Customer package and lot photo reviewed; forwarding for importer trace.",
        },
    )
    assert retailer_review.status_code == 200, retailer_review.text
    assert retailer_review.json()["idempotent"] is False
    repeated_review = client.post(
        f"/api/v1/cases/{retailer_case['id']}/retailer-review",
        json={"decision": "forwarded", "notes": "Repeated submission."},
    )
    assert repeated_review.json()["idempotent"] is True

    _logout(client)
    login_user(client, "retailer-b@escalera.demo")
    forbidden_review = client.post(
        f"/api/v1/cases/{retailer_case['id']}/retailer-review",
        json={"decision": "forwarded", "notes": "Wrong retailer attempt."},
    )
    assert forbidden_review.status_code == 404

    _logout(client)
    login_user(client, "importer@escalera.demo")
    cases = client.get("/api/v1/cases")
    assert cases.status_code == 200
    case = next(item for item in cases.json() if item["public_id"] == report.json()["case_id"])

    assert client.post(f"/api/v1/cases/{case['id']}/analysis").status_code == 409
    triage_proposal = client.get(f"/api/v1/cases/{case['id']}").json()["proposals"][0]
    assert triage_proposal["status"] == "pending"
    assert (
        client.post(
            f"/api/v1/cases/{case['id']}/approvals",
            json={"proposal_id": triage_proposal["id"], "decision": "approved"},
        ).status_code
        == 200
    )
    start = client.post(f"/api/v1/cases/{case['id']}/analysis")
    assert start.status_code == 202, start.text
    run_id = start.json()["run_id"]

    analysis = None
    for _ in range(100):
        analysis = client.get(f"/api/v1/cases/{case['id']}/analysis/{run_id}")
        assert analysis.status_code == 200
        if analysis.json()["status"] in {"awaiting_human", "failed"}:
            break
        time.sleep(0.05)
    assert analysis.json()["status"] == "awaiting_human", analysis.json()
    proposal = analysis.json()["result"]
    assert proposal["type"] == "retailer_inspections"
    assert proposal["batch"]["quantity_received"] == 10_000
    assert proposal["batch"]["quantity_retained"] == 4_000
    assert [row["retailer_code"] for row in proposal["retailers"]] == [
        "RETAILER-A",
        "RETAILER-B",
        "RETAILER-C",
    ]
    assert [row["retailer_code"] for row in proposal["excluded_retailers"]] == ["RETAILER-D"]

    _logout(client)
    login_user(client, "retailer-a@escalera.demo")
    assert all(item["case_id"] != case["id"] for item in client.get("/api/v1/inspections").json())
    _logout(client)
    login_user(client, "importer@escalera.demo")

    approval = client.post(
        f"/api/v1/cases/{case['id']}/approvals",
        json={
            "proposal_id": analysis.json()["proposal_id"],
            "decision": "approved",
            "notes": "Shipment evidence verified by importer investigator.",
        },
    )
    assert approval.status_code == 200, approval.text
    repeat = client.post(
        f"/api/v1/cases/{case['id']}/approvals",
        json={
            "proposal_id": analysis.json()["proposal_id"],
            "decision": "approved",
        },
    )
    assert repeat.json()["idempotent"] is True
    detail = client.get(f"/api/v1/cases/{case['id']}").json()
    assert any(event["event_type"] == "retailer_review_submitted" for event in detail["timeline"])
    blocked_escalation = client.post(f"/api/v1/cases/{case['id']}/escalation-analysis")
    assert blocked_escalation.status_code == 409

    _logout(client)
    login_user(client, "retailer-a@escalera.demo")
    inspections = client.get("/api/v1/inspections")
    assert inspections.status_code == 200
    inspection = next(item for item in inspections.json() if item["case_id"] == case["id"])
    finding = client.post(
        f"/api/v1/inspections/{inspection['id']}/finding",
        json={
            "finding": "issue_observed",
            "notes": "Food safety manager isolated one matching bar with the same visible issue.",
        },
    )
    assert finding.status_code == 200, finding.text

    _logout(client)
    login_user(client, "importer@escalera.demo")
    assert client.post(f"/api/v1/cases/{case['id']}/escalation-analysis").status_code == 409
    for account in ("retailer-b@escalera.demo", "retailer-c@escalera.demo"):
        _logout(client)
        login_user(client, account)
        task = next(
            row for row in client.get("/api/v1/inspections").json() if row["case_id"] == case["id"]
        )
        assert (
            client.post(
                f"/api/v1/inspections/{task['id']}/finding",
                json={
                    "finding": "no_issue_observed",
                    "notes": "Matching lot physically checked; no visible issue.",
                },
            ).status_code
            == 200
        )
    _logout(client)
    login_user(client, "importer@escalera.demo")
    escalation_start = client.post(f"/api/v1/cases/{case['id']}/escalation-analysis")
    assert escalation_start.status_code == 202, escalation_start.text
    escalation_run_id = escalation_start.json()["run_id"]
    for _ in range(100):
        escalation_analysis = client.get(f"/api/v1/cases/{case['id']}/analysis/{escalation_run_id}")
        assert escalation_analysis.status_code == 200
        if escalation_analysis.json()["status"] in {"awaiting_human", "failed"}:
            break
        time.sleep(0.05)
    assert escalation_analysis.json()["status"] == "awaiting_human", escalation_analysis.json()
    escalation_proposal = escalation_analysis.json()["result"]
    assert escalation_proposal["type"] == "manufacturer_escalation_packet"
    assert escalation_proposal["completed_inspections"] == 3
    assert escalation_proposal["recommendation"] == "prepare_manufacturer_escalation"
    assert any(
        call["tool"] == "get_inspection_findings" for call in escalation_proposal["tool_calls"]
    )
    assert {call["tool"] for call in escalation_proposal["tool_calls"]} >= {
        "get_distribution_summary",
        "get_case_timeline",
    }
    assert "customer@example.com" not in str(escalation_proposal)

    escalation_approval = client.post(
        f"/api/v1/cases/{case['id']}/approvals",
        json={
            "proposal_id": escalation_analysis.json()["proposal_id"],
            "decision": "approved",
            "notes": "Please investigate production and ingredient records for lot 38.",
        },
    )
    assert escalation_approval.status_code == 200, escalation_approval.text
    assert client.post(f"/api/v1/cases/{case['id']}/escalation-analysis").status_code == 409

    _logout(client)
    login_user(client, "manufacturer@escalera.demo")
    assert client.get("/api/v1/cases").status_code == 403
    inbox = client.get("/api/v1/escalations")
    assert inbox.status_code == 200
    manufacturer_case = next(item for item in inbox.json() if item["case_id"] == case["id"])
    assert "reporter_email" not in str(manufacturer_case["packet"])
    csv_report = client.get(
        f"/api/v1/escalations/{manufacturer_case['id']}/report.csv"
    )
    assert csv_report.status_code == 200
    assert "text/csv" in csv_report.headers["content-type"]
    assert "manufacturer-report.csv" in csv_report.headers["content-disposition"]
    report_rows = list(csv.DictReader(io.StringIO(csv_report.text.lstrip("\ufeff"))))
    assert any(
        row["Section"] == "Distribution"
        and row["Retailer"] == "CityMart Islamabad"
        and row["Quantity"] == "3000"
        for row in report_rows
    )
    assert any(
        row["Section"] == "Retailer finding"
        and row["Status"] == "Issue Observed"
        for row in report_rows
    )
    assert "customer@example.com" not in csv_report.text
    packet_evidence = manufacturer_case["packet"]["evidence"]
    assert packet_evidence[0]["filename"] == "package.png"
    evidence_download = client.get(f"/api/v1/evidence/{packet_evidence[0]['id']}")
    assert evidence_download.status_code == 200
    assert evidence_download.content == evidence_content
    response = client.post(
        f"/api/v1/escalations/{manufacturer_case['id']}/response",
        json={
            "response": "Lot 38 is under internal investigation; distribution hold acknowledged."
        },
    )
    assert response.status_code == 200, response.text

    _logout(client)
    login_user(client, "importer@escalera.demo")
    closed = client.patch(
        f"/api/v1/cases/{case['id']}/status",
        json={
            "status": "closed",
            "safety_verdict": "confirmed",
            "notes": "Reviewed manufacturer response and retailer findings.",
        },
    )
    assert closed.status_code == 200

    final_tracking = client.get(f"/api/v1/tracking/{tracking_token}")
    assert final_tracking.json()["status"] == "closed"
    assert final_tracking.json()["safety_verdict"] == "confirmed"


def test_unknown_batch_requests_human_information_followup(client, login_user):
    report = client.post(
        "/api/v1/reports",
        json={
            "product_name": "SweetCo Alpine Milk Chocolate 100g",
            "description": (
                "The package was damaged, but I cannot read the manufacturer lot number."
            ),
        },
    )
    assert report.status_code == 201
    login_user(client, "importer@escalera.demo")
    case = next(
        item
        for item in client.get("/api/v1/cases").json()
        if item["public_id"] == report.json()["case_id"]
    )
    triage = client.get(f"/api/v1/cases/{case['id']}").json()
    triage_proposal = next(
        item for item in triage["proposals"] if item["type"] == "triage_recommendation"
    )
    triage_approval = client.post(
        f"/api/v1/cases/{case['id']}/approvals",
        json={"proposal_id": triage_proposal["id"], "decision": "approved"},
    )
    assert triage_approval.status_code == 200, triage_approval.text
    start = client.post(f"/api/v1/cases/{case['id']}/analysis")
    assert start.status_code == 409
    assert "requested information" in start.json()["detail"]
    updated = client.post(
        f"/api/v1/cases/{case['id']}/information",
        json={"batch_number": "38", "notes": "Readable packaging photo confirms lot 38."},
    )
    assert updated.status_code == 200
    assert client.post(f"/api/v1/cases/{case['id']}/analysis").status_code == 409


def test_traceability_requires_triage_human_approval(client, login_user):
    report = client.post(
        "/api/v1/reports",
        json={
            "retailer_code": "RETAILER-A",
            "product_name": "SweetCo Alpine Milk Chocolate 100g",
            "batch_number": "38",
            "description": "The package appears damaged and I want it reviewed.",
        },
    )
    assert report.status_code == 201
    login_user(client, "importer@escalera.demo")
    case = next(
        item
        for item in client.get("/api/v1/cases").json()
        if item["public_id"] == report.json()["case_id"]
    )
    response = client.post(f"/api/v1/cases/{case['id']}/analysis")
    assert response.status_code == 409
    assert "approve its latest proposal" in response.json()["detail"]
