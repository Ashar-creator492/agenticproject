# Escalera API reference

All application endpoints are under `/api/v1` except health checks, the root response, OpenAPI JSON,
and Swagger UI. The running server provides the authoritative interactive contract at `/docs`.

## Public endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | Database readiness |
| `POST` | `/api/v1/reports` | Create a customer report and tracking token |
| `POST` | `/api/v1/reports/photo` | Atomically submit supermarket, description and 1–3 JPEG/PNG photos; no customer product/batch entry |
| `GET` | `/api/v1/tracking/{tracking_token}` | View public case progress |
| `POST` | `/api/v1/reports/{public_id}/evidence` | Upload report evidence with the tracking token |

Evidence uploads accept JPEG, PNG, or PDF files up to 5 MB.

## Authentication

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Create a server-side session cookie |
| `POST` | `/api/v1/auth/logout` | Revoke the current session |
| `GET` | `/api/v1/auth/me` | Return the signed-in staff user |

Browser clients must send cookies on authenticated requests.

## Shared staff endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/cases` | List role-scoped cases |
| `GET` | `/api/v1/cases/{case_id}` | Read case detail, evidence, proposals, findings, escalation, and timeline |
| `POST` | `/api/v1/cases/{case_id}/evidence` | Add authenticated evidence |
| `GET` | `/api/v1/evidence/{evidence_id}` | Download evidence when authorized |
| `GET` | `/api/v1/catalog/retailers` | List permitted retailer choices |
| `GET` | `/api/v1/catalog/products` | Search catalogue products |
| `GET` | `/api/v1/catalog/batches` | List role-scoped batches |
| `GET` | `/api/v1/catalog/shipments` | List role-scoped shipments |

## Retailer endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/cases/officer-report` | Create a case from a retailer inspection |
| `POST` | `/api/v1/cases/{case_id}/triage` | Run or retrieve the bounded triage agent |
| `POST` | `/api/v1/cases/{case_id}/retailer-review` | Review and forward or hold a customer report |
| `POST` | `/api/v1/cases/{case_id}/demo-barcode` | Officer-only preview of a fictional barcode-to-product/lot mapping for the case's supermarket |
| `GET` | `/api/v1/inspections` | List inspections assigned to the signed-in retailer |
| `POST` | `/api/v1/inspections/{inspection_id}/finding` | Submit a human stock-check finding |

## Importer endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/organizations` | List manufacturer and retailer organizations |
| `POST` | `/api/v1/organizations` | Create a manufacturer or retailer with its first role-scoped staff login |
| `GET` | `/api/v1/imports/templates/{kind}` | Download a batch or shipment CSV template |
| `POST` | `/api/v1/imports/batches` | Validate and import batch records |
| `POST` | `/api/v1/imports/shipments` | Validate and import shipment records |
| `PATCH` | `/api/v1/cases/{case_id}/status` | Update permitted state or final human verdict with response/notes prerequisites |
| `POST` | `/api/v1/cases/{case_id}/information` | Save investigation facts/corrections; invalidate prior input snapshots |
| `POST` | `/api/v1/cases/{case_id}/analysis` | Queue the MCP-grounded traceability agent |
| `POST` | `/api/v1/cases/{case_id}/escalation-analysis` | Queue escalation after every assigned retailer responds |
| `GET` | `/api/v1/cases/{case_id}/analysis/{run_id}` | Poll investigation status and result |
| `POST` | `/api/v1/cases/{case_id}/approvals` | Approve or reject an agent proposal |
| `POST` | `/api/v1/escalations/cases/{case_id}` | Retrieve an existing escalation; creation requires case proposal approval |

Manufacturer escalation requires an approved traceability proposal, completed findings from every assigned retailer, and importer approval of the escalation-agent packet.

Organization creation accepts `code`, `name`, `type` (`retailer` or `manufacturer`),
`staff_name`, `staff_email`, and `staff_password` (at least 12 characters). Codes are stored
uppercase. The password is hashed and never returned. Duplicate codes or emails are rejected.
Create organizations before importing CSVs that refer to their codes.

For photo reports (`source=customer_photo`), triage starts after officer verification and forwarding.
The photo endpoint accepts multipart fields `retailer_code`, `description`, optional `reporter_name`,
`reporter_email`, `purchase_date`, and repeated `files`. Files must be JPEG/PNG, at most 5 MB each.
All photos are validated before anything is saved.

The barcode endpoint takes `{"barcode":"DEMO-CHOC-38"}` and returns `simulated`, product and batch
identifiers, SKU, product name, and batch number. It checks the supermarket received that batch.
Forwarding a photo case requires `demo_barcode` in the retailer-review request, alongside `decision`
and `notes`; the server revalidates the match and records `demo_barcode_verified`. A lookup alone
does not update the case. Case detail now includes `evidence`, `retailer_review`, and
`demo_verification`. Evidence URLs remain authenticated and scoped to authorized staff.

Triage is automatically queued on creation for legacy structured and retailer reports. Retailer staff
can also run triage and forward or hold a customer report. Traceability can start after retailer
forwarding (for photo reports) and explicit importer approval of the latest triage proposal. Only the importer can approve proposals, create retailer
checks, or approve the manufacturer packet. A traceability proposal creates checks only when
approved; escalation analysis requires the current approved traceability result and completed
findings from every assigned retailer.

## Manufacturer endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/escalations` | List escalations addressed to the signed-in manufacturer |
| `POST` | `/api/v1/escalations/{escalation_id}/response` | Submit the manufacturer investigation response |

## MCP tools

The stdio server in `backend/app/mcp_server.py` exposes these read-only tools:

- `get_case(case_id)`
- `search_products(query)`
- `get_batch(product_id, batch_number)`
- `find_related_reports(product_id, batch_number, exclude_case_id)`
- `get_batch_shipments(batch_id)`
- `get_non_recipient_retailers(batch_id)`
- `get_inspection_findings(case_id)`
- `get_approved_traceability(case_id)`
- `get_case_evidence_metadata(case_id)`
- `get_case_timeline(case_id)`
- `get_distribution_summary(batch_id)`

Tool output preserves database identifiers. Reporter contact details are intentionally absent.

In `AGENT_MODE=llm`, triage uses Groq to select tools and submit a validated proposal. Its
results include `execution_mode=llm`, `model`, `llm_turns`, and `ai_assessment`. Explicit offline
triage uses `execution_mode=demo_rules`. Traceability and escalation always return
`execution_mode=rules`, `model=null`, rationale, evidence references, and successful MCP traces.
All stage routes, role checks, and human approvals remain the same. Long Groq quota waits fail
with a provider retry time; rule-based stages never call Groq.

### Per-agent tool allowlists

| Agent | MCP tools available |
| --- | --- |
| Triage | `get_case`, `search_products`, `find_related_reports` |
| Traceability | `get_case`, `search_products`, `get_batch`, `find_related_reports`, `get_batch_shipments`, `get_non_recipient_retailers`, `get_distribution_summary` |
| Escalation | `get_case`, `get_approved_traceability`, `get_batch_shipments`, `get_inspection_findings`, `get_case_evidence_metadata`, `get_case_timeline`, `get_distribution_summary` |

The MCP server is read-only. Approvals, task creation, escalation delivery, and final verdicts are
performed by role-checked API handlers and recorded in the case timeline.

## Backend workflow enforcement (2026-10-16)

- Every triage result requires a new importer approval; supermarket forwarding is a separate decision.
- Approvals apply only to the latest run and its saved input versions. Old decisions never approve new results.
- Traceability requires current approved triage without an outstanding information request.
- Escalation requires a current approved shipment plan and completed findings from all assigned supermarkets.
- More-check recommendations reopen the selected supermarket tasks after approval; monitoring sends no manufacturer packet.
- Only an approved manufacturer-escalation recommendation creates the manufacturer inbox item.
- `POST /api/v1/cases/{id}/information` accepts notes and optional corrected product_name/batch_number.
  Saving information invalidates earlier proposals; rerun triage and review the new result.
  Identity corrections are blocked once retailer tasks exist.
- Case detail includes backend-authoritative `workflow` gates, proposal `review_block_reason`,
  named supermarket progress, and the manufacturer's response.
- Final verdict/closure requires a manufacturer response and reviewer notes. Operational statuses
  cannot bypass proposal approvals through the status endpoint.
- Existing historical decisions are retained. Runs predating input snapshots need a new run and review.
- Notifications remain in-app task queues; external email/SMS dispatch is not implemented.
