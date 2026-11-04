# Escalera implementation plan

## Phase 0: scope and acceptance criteria

- [x] Define the importer as system owner.
- [x] Support direct customer reports and retailer-originated inspection reports.
- [x] Separate suspected reports from confirmed human safety decisions.
- [x] Require human approval for retailer tasks, manufacturer escalation, and the final verdict.
- [x] Define the lot `38` demonstration and negative control using Retailer D on lot `39`.

## Phase 1: project and data foundation

- [x] Create the FastAPI project, configuration, packaging, and container contract.
- [x] Model organizations, users, products, aliases, batches, shipments, cases, evidence, agent runs,
  proposals, approvals, reviews, inspections, escalations, and audit events.
- [x] Add Alembic migration support for PostgreSQL and SQLite.
- [x] Seed fictional organizations, accounts, products, lots, and distribution records.
- [x] Add batch and shipment CSV templates and validated imports.
- [x] Add importer-managed manufacturer/retailer setup, first staff logins, and clean-database importer bootstrap.

## Phase 2: identity and safety controls

- [x] Add password-protected staff accounts and server-side sessions.
- [x] Enforce importer, retailer, and manufacturer roles and organization scope.
- [x] Hash session and public tracking tokens.
- [x] Add origin checks for authenticated mutations.
- [x] Restrict uploads to JPEG, PNG, and PDF with a 5 MB limit.
- [x] Exclude customer contact details from MCP, model, and manufacturer payloads.

## Phase 3: operational workflow

- [x] Implement customer reporting and private tracking.
- [x] Implement retailer-created inspection reports and customer complaint review.
- [x] Implement importer case queue, detail view contract, state changes, and verdict updates.
- [x] Implement retailer inspection assignments and findings.
- [x] Implement manufacturer evidence packets and responses.
- [x] Add an append-only case audit timeline.

## Phase 4: agent and MCP

- [x] Implement a read-only MCP stdio server for cases, products, batches, related reports,
  shipments, and inspection findings.
- [x] Implement the LangGraph investigation workflow.
- [x] Split the workflow into triage, traceability, and escalation agents.
- [x] Add structured results and per-agent MCP tool allowlists.
- [x] Require a second importer approval for the escalation-agent evidence packet.
- [x] Keep exact shipment matching deterministic and database-backed.
- [x] Add bounded Groq tool-calling triage with evidence validation.
- [x] Replace active traceability/escalation LLM calls with MCP-backed rule-based stages.
- [x] Remove traceability/escalation API-key slots and label rule execution accurately.
- [x] Add input snapshots, fresh approval gates, changed-input UI guidance, and quota errors.
- [x] Verify no-model rule stages and manufacturer/follow-up/monitoring outcomes.
- [x] Validate model decisions against MCP evidence; never accept invented shipment recipients.
- [x] Label execution mode and require explicit demo mode for offline simulations.
- [x] Store runs, proposals, confidence, evidence, and errors.
- [x] Enforce an explicit human approval boundary before any proposed action is applied.
- [x] Expose per-agent MCP tool-call traces in the case detail response and frontend.

## Phase 5: verification

- [x] Test authorization boundaries and organization scoping.
- [x] Test the public-to-importer-to-retailer-to-manufacturer workflow.
- [x] Test CSV imports and exact product-plus-lot matching.
- [x] Prove that Retailer D is excluded from lot `38` results.
- [x] Run Ruff, 35 backend tests, and the frontend TypeScript/Vite build successfully.
- [x] Verify live local MCP traceability and escalation without Groq requests.
- [ ] Run a container smoke check on a machine with Docker available.

## Phase 6: responsive frontend

- [x] Create the React, TypeScript, Vite, and Tailwind application.
- [x] Define a typed API client for `/api/v1`.
- [x] Build the public report form.
- [x] Add the private tracking-token lookup screen.
- [x] Build staff login and role-specific navigation.
- [x] Build importer case detail, agent trace, approvals, and timeline.
- [x] Build importer CSV import screens.
- [x] Make organization setup and imports accessible before any case exists; show imported records and row errors.
- [x] Expose retailer-originated report creation in the frontend for imported products and lots.
- [x] Build retailer complaint review, assigned inspection, and finding screens.
- [x] Build manufacturer escalation inbox and response screen.
- [x] Add loading, error, and empty states.
- [ ] Complete browser-based keyboard and viewport verification.

## Phase 7: Alternate Clouds deployment

- [x] Add Dockerfile, health endpoints, environment contract, and deployment guide.
- [x] Push the repository to GitHub on `main`.
- [ ] Confirm the current GitHub repository is connected to the Alternate Clouds application service.
- [ ] Create a PostgreSQL 17 template service with persistent storage.
- [ ] Create a GitHub application service using `batchbridge` as the root directory.
- [ ] Link PostgreSQL to the application with alias `DB`.
- [ ] Set `APP_BASE_URL`, `SESSION_SECRET`, triage `GROQ_TRIAGE_API_KEY` or `GROQ_API_KEY`,
  `GROQ_MODEL`, `AGENT_MODE`, `COOKIE_SECURE`,
  `ALLOWED_ORIGINS`, `SEED_DEMO_DATA`, and `DEMO_PASSWORD`.
- [ ] Follow the required order: set variables, rebuild, then deploy.
- [ ] Verify liveness, readiness, login, migrations, the full demo, and persistence after redeploy.

## Phase 8: submission

- [ ] Rehearse `DEMO_RUNBOOK.md` against the deployed URL.
- [ ] Record the deployed URL, repository URL, test result, and architecture summary.
- [ ] Capture screenshots or a short backup recording.
- [ ] Prepare a concise pitch: problem, affected actors, MCP grounding, human gates, live workflow,
  and international expansion path.
- [ ] Submit before the organizer deadline.

## Post-hackathon backlog

- [ ] Connect retailer and importer ERP systems.
- [ ] Add barcode and OCR-assisted lot capture with human verification.
- [ ] Add multilingual reporting and notifications.
- [ ] Add regulator integrations where legally available.
- [ ] Add laboratory result records, formal recall workflows, and jurisdiction-specific policies.
- [ ] Add multi-importer tenancy, managed object storage, backup policy, and disaster recovery.
