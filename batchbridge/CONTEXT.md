# Escalera — current project context

Updated: 2026-10-17. This file describes the current implementation, superseding earlier
plans for three LLM-powered stages. See `IMPLEMENTATION_STATUS.md` for the detailed handoff.

## Product and ownership

Escalera is an importer-owned food complaint and batch investigation application.
The importer maintains products, manufacturer lots, received quantities, and retailer shipments.
The workflow links one suspected customer issue to the exact recorded distribution chain.
A complaint, photo, or visual inspection does not prove contamination. Humans control tasks,
manufacturer handoffs, final verdicts, and closure.

## Current execution model

| Stage | Execution | Groq required? | Human checkpoint |
| --- | --- | --- | --- |
| Triage | Bounded LLM tool-calling investigation; explicit offline simulation available | Yes in `AGENT_MODE=llm` | Importer reviews the latest triage proposal |
| Traceability | Deterministic matching and MCP database lookups | No | Importer approves retailer tasks |
| Escalation | Deterministic evidence aggregation and recommendation rules | No | Importer approves packet, follow-up checks, or monitoring |
| Manufacturer response | Authenticated human reviewer | No | Manufacturer submits its response |
| Verdict and closure | Authenticated importer | No | Importer records the decision and notes |

All three investigation stages still run through the existing LangGraph workflow and persisted
proposal/human-interrupt mechanism. Traceability and escalation are rule-based workflow stages,
not LLM reasoning agents. Do not describe the current system as three LLM-powered agents.
MCP is a tool-access protocol, independent of the number of agents or models.

## Roles and interfaces

The public `/how-it-works` page follows the supplied “How it works (light)” PDF: a four-step
overview, three investigation stages with importer approval points, shop findings, summary figures,
and a role permissions table. It is one scrollable page with a responsive stacked workflow and a
keyboard-scrollable permissions table on small screens. The page also clarifies the existing triage
review before tracing; the two highlighted importer approvals govern shop tasks and escalation.
This is frontend explanatory content only; backend permissions and workflow gates are unchanged.

- Customer: public photo complaint, supermarket selection, description, optional contact/date,
  private tracking token. Customers do not need to identify a lot themselves.
- Supermarket food safety manager: internal retailer staff, not a government officer. Verifies
  product identity, forwards customer complaints, creates officer reports, completes assigned checks.
- Importer investigator: imports batch/shipment CSVs, runs investigations, reviews proposals,
  coordinates supermarket checks, approves manufacturer packets, records the final verdict.
  The importer can create retailer/manufacturer organizations with an initial staff account.
- Manufacturer reviewer: accesses packets addressed to its organization and submits a response.

## End-to-end workflow

1. A photo report stores a case and 1–3 validated JPEG/PNG images atomically, without starting triage.
2. The originating supermarket previews a simulated barcode lookup, confirms product/lot identity,
   and forwards the complaint. Forwarding starts triage; it does not approve triage's recommendation.
3. Triage reads case/catalogue/related-report evidence through MCP and proposes the next action.
4. The importer explicitly approves the latest triage proposal. An information request must be
   answered and followed by a new triage run and review before tracing.
5. Traceability resolves exact SKU/name/known alias plus manufacturer lot, reads shipments,
   excludes nonrecipients, and proposes retailer checks from canonical database records.
6. Importer approval creates in-app inspection tasks. Each assigned supermarket submits a finding.
7. Escalation waits for findings from every recipient in the current approved shipment plan.
8. Rule-based escalation proposes a manufacturer packet if any issue was observed; otherwise
   targets inconclusive findings for follow-up, or recommends monitoring if none remain.
9. Importer approval applies the proposed action. A manufacturer packet appears in the scoped inbox;
   follow-up reopens only selected inspections; monitoring creates no manufacturer packet.
10. The manufacturer responds. The importer reviews the response, records a verdict and notes,
    and closes the case. Public tracking reflects the final state.

Legacy structured reports and officer-created reports start triage on creation.
The retailer UI now exposes officer-created reports for imported products and lots; this is the
own-data intake path while public photo verification remains a simulated barcode demo.
No email/SMS or external manufacturer dispatch is implemented; communication uses portal queues.

## Safety and approval invariants

- Match a batch by product plus lot, never lot alone. No single-search-result shortcut is accepted
  by the rule-based traceability matcher; it needs an exact SKU, name, or known alias.
- All recipient identifiers and quantities come from actual shipment records through MCP.
- One shared stdio MCP server exposes 11 read-only tools with stage-specific allowlists.
- MCP cannot create tasks, approve proposals, send packets, or record verdicts.
- Approvals are immutable decisions tied to a proposal. An identical retry is idempotent;
  a different decision for the same proposal is rejected.
- `AgentRun.input_snapshot` captures identity, information revision, and relevant upstream proposal
  versions; escalation also tracks evidence/finding revisions. Earlier approvals never authorize
  newer runs or changed inputs.
- Saving additional investigation facts invalidates prior input snapshots. Rerun triage and review
  the new proposal. Identity changes are blocked after inspection tasks exist.
- A changed shipment plan must be traced and reviewed again before escalation.
- Final verdict/closure requires a manufacturer response and notes. Operational status updates
  cannot bypass task or packet approvals.
- Reporter contact details are excluded from MCP and manufacturer packets.

## Rules for traceability and escalation

Traceability requests information for unresolved product, missing lot, unknown importer batch,
or absent shipment records. A successful proposal includes recipients, excluded retailers,
related reports, confidence, matching rationale, evidence references, and MCP calls.
It does not require laboratory confirmation, recall status, or prior inspection findings.

Escalation requires current approved traceability and completed findings from all recipients:

| Findings | Proposal type | Approved effect |
| --- | --- | --- |
| At least one `issue_observed` | `manufacturer_escalation_packet` | Create manufacturer inbox item |
| No observed issue, at least one `unable_to_assess` | `retailer_followup` | Reopen the selected inconclusive checks |
| No observed or inconclusive issue | `monitoring` | Record the review; no manufacturer packet |

Conflicting visual findings are included in the evidence packet. Neither an observed issue nor a
negative inspection automatically establishes the safety of the entire lot.

## Configuration and runtime

- Backend: FastAPI, SQLAlchemy, Alembic; SQLite locally, PostgreSQL planned for deployment.
- Frontend: React, TypeScript, Vite, Tailwind. Built assets are served by FastAPI when available.
- Local app: `http://localhost:8000`; separate Vite development server: `http://localhost:5173`.
- Groq model: `GROQ_MODEL`, currently defaulting to `openai/gpt-oss-20b`.
- Only triage uses `GROQ_TRIAGE_API_KEY`, falling back to `GROQ_API_KEY` when blank.
- Traceability/escalation key slots were removed from `.env`, `.env.example`, and Settings.
  Those stages always use rules, independent of `AGENT_MODE` and Groq availability.
- `AGENT_MODE=demo` selects offline triage simulation. It does not change the two rule-based stages.
- Restart after changing `.env`; never print, stage, or commit secrets.
- Long Groq cooldowns (>45 seconds) produce an explicit retry-time error instead of repeated
  shortened waits. LLM failures never silently turn into demo decisions.
- UI execution tags are `llm`, `rules`, or historical `demo_rules`. Old results keep their history;
  pending proposals from another execution mode can be superseded by rerunning the stage.

## Fictional demo fixture

Product `CHOC-100`: SweetCo Alpine Milk Chocolate 100g; manufacturer SweetCo GmbH.
Lot 38: 10,000 received; CityMart A 3,000, FreshBasket B 2,000, Family Grocer C 1,000,
4,000 retained. Value Market D received lot 39 only and must be excluded from lot 38 checks.
`DEMO-CHOC-38` and `DEMO-CHOC-39` are simulated mappings, not image decoding or OCR.
Two generated fictional photos are in `examples/demo-evidence/`.

Seeded logins: `importer@escalera.demo`, `retailer-a@escalera.demo`,
`retailer-b@escalera.demo`, `retailer-c@escalera.demo`, `manufacturer@escalera.demo`.
Eight stable fictional complaints (`ESC-DEMO-001` through `ESC-DEMO-008`) are added idempotently when
demo seeding is enabled. Each has a named reporter, retailer, lot `38`, distinct complaint text, and
an officer-forwarded review so it can enter the importer workflow without repeating retailer intake.
Manufacturer packets render as plain-language sections and tables. After importer approval, the
manufacturer and importer can download a UTF-8 CSV report from the scoped escalation endpoint. The
CSV contains product/lot identity, distribution, human findings, evidence metadata, requested
actions, and importer notes; customer contact data remains excluded.
Passwords come from `DEMO_PASSWORD`; production credentials must be set through deployment secrets.
All five local demo account hashes were synchronized with the current ignored `.env` value.
Login validates a non-empty password rather than imposing a password-creation length rule;
short configured demo credentials work in both the UI and API. Stored passwords remain hashed.
Local resets retain seed accounts/catalogue/shipments and clear complaints and workflow history,
after a backup. Database files and backups are not part of Git.

## Verification and latest local handoff

36 backend tests passed, Ruff passed, frontend TypeScript/Vite build passed.
All five local demo accounts passed live API login, authenticated session, and logout checks
after the demo password update. Environment values and database hashes remain local, outside Git.
A live MCP check returned the expected three retailers for lot 38 without a model call.
The latest local test case `ESC-19BB1B3CA0` produced a rule-based manufacturer packet awaiting
importer approval. This is local state only, not seeded or committed data, and can change in use.
No reset is needed to use the rule-based stages; existing approvals/findings are preserved.

## Known limitations and next work

- No real barcode decoding, OCR, ERP integration, email/SMS delivery, regulator connection, or
  laboratory integration. No autonomous contamination diagnosis or recall.
- Explicit demo seed data is fictional; the system's conclusions depend on connected records.
- In-process execution and in-memory graph checkpoints are not a distributed worker system.
  Database decisions are authoritative, and queued/running runs are recovered at startup.
- Monitoring has no scheduled follow-up worker; a human decides the next action.
- Multi-importer tenancy, managed backups, and production scaling remain future work.
- Alternate Clouds deployment, container smoke test, persistence verification, and browser
  keyboard/viewport checks remain unverified. See deployment checklist; do not claim them complete.
