from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserView(ApiModel):
    id: str
    email: str
    display_name: str
    role: str
    organization_id: str


class OrganizationCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=200)
    type: Literal["retailer", "manufacturer"]
    staff_name: str = Field(min_length=2, max_length=120)
    staff_email: EmailStr
    staff_password: str = Field(min_length=12, max_length=200)


class OrganizationView(ApiModel):
    id: str
    code: str
    name: str
    type: str


class ReportCreate(BaseModel):
    reporter_name: str | None = Field(default=None, max_length=120)
    reporter_email: EmailStr | None = None
    retailer_code: str | None = Field(default=None, max_length=40)
    product_name: str = Field(min_length=2, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    purchase_date: date | None = None
    description: str = Field(min_length=10, max_length=5000)


class ReportCreated(BaseModel):
    case_id: str
    tracking_token: str
    tracking_url: str
    status: str


class TrackingView(BaseModel):
    case_id: str
    product_name: str
    status: str
    safety_verdict: str
    created_at: datetime
    updated_at: datetime


class CaseSummary(ApiModel):
    id: str
    public_id: str
    source: str
    reporter_name: str | None
    product_name: str
    batch_number: str | None
    status: str
    safety_verdict: str
    retailer_id: str | None
    created_at: datetime
    updated_at: datetime


class OfficerReportCreate(BaseModel):
    product_name: str = Field(min_length=2, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    description: str = Field(min_length=10, max_length=5000)
    purchase_date: date | None = None


class AnalysisStartResponse(BaseModel):
    run_id: str
    status: str
    agent_type: Literal["triage", "traceability", "escalation"]


class ApprovalRequest(BaseModel):
    proposal_id: str
    decision: Literal["approved", "rejected", "changes_requested"]
    notes: str | None = Field(default=None, max_length=2000)


class RetailerReviewRequest(BaseModel):
    decision: Literal["forwarded", "needs_customer_information", "unable_to_verify"]
    notes: str = Field(min_length=3, max_length=5000)
    demo_barcode: str | None = Field(default=None, max_length=100)


class DemoBarcodeRequest(BaseModel):
    barcode: str = Field(min_length=1, max_length=100)


class FindingRequest(BaseModel):
    finding: Literal["issue_observed", "no_issue_observed", "unable_to_assess"]
    notes: str = Field(min_length=3, max_length=5000)


class EscalationCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class ManufacturerResponseCreate(BaseModel):
    response: str = Field(min_length=3, max_length=5000)


class CsvImportResult(BaseModel):
    inserted: int
    skipped: int
    errors: list[dict[str, Any]]


class CaseInformationCreate(BaseModel):
    notes: str = Field(min_length=3, max_length=5000)
    product_name: str | None = Field(default=None, min_length=2, max_length=200)
    batch_number: str | None = Field(default=None, min_length=1, max_length=100)


class StatusUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal[
        "under_review",
        "waiting_for_information",
        "retailer_checks",
        "manufacturer_review",
        "closed",
    ]
    safety_verdict: Literal["unconfirmed", "suspected", "confirmed", "not_supported"] | None = None
