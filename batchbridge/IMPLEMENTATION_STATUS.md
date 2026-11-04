# Escalera implementation handoff

Updated: 2026-10-17. This describes completed code and local verification, not a claim of
production deployment. Stable operating context is in `CONTEXT.md`.

## Own-data setup update (2026-11-04)

- A fresh database can run with `SEED_DEMO_DATA=false`; `python -m app.bootstrap_importer`
  prompts for the first importer organization and account after migrations.
- Importers can create a manufacturer or retailer with an initial, role-scoped staff account.
  The Data setup screen is available even when no cases exist, shows organizations and imported
  records, and provides batch/shipment CSV templates and row errors.
- Retailer staff can file a new suspected-issue report from the UI using an imported product and
  manufacturer lot. This gives own-data records a complete in-app investigation path without
  relying on the demo barcode mapping.
- Existing databases were not reset or altered for this change. The demo seed is unchanged for
  complete demo fixtures and skips adding demo complaints to an incomplete custom catalogue.
- Current verification: Ruff passed, 41 backend tests passed, and the TypeScript/Vite production
  build passed. A new integration test runs imported records through triage, exact-lot tracing,
  retailer finding, manufacturer response, and importer closure.

## 1. Why the workflow changed

The initial implementation used Groq tool-calling for all three stages. Local testing exposed
three separate classes of failures: stale approvals were confusing in the UI, models sometimes
blocked tracing on downstream lab questions, and quota waits caused slow/failed runs.

The current design keeps language interpretation in triage and makes exact tracing and evidence
aggregation deterministic. These stages still query real application records through MCP and
produce reviewable proposals; no test-case-specific recipients or verdicts are injected.

## 2. Completed functionality

### Intake and identity verification

- Public photo form accepts supermarket, description, optional contact/purchase date, and 1–3
  JPEG/PNG files of at most 5 MB each.
- Intake validates all files before storing the case/evidence, preventing partial photo submissions.
- A demo packaging helper and two generated fictional images support repeatable demonstrations.
- Supermarket staff preview a simulated barcode mapping and explicitly forward the verified case.
- Verification updates product/lot identity and audit history; it does not confirm contamination.
- Existing structured reports and officer-originated reports remain supported.

### Triage

- Uses the assigned Groq credential in LLM mode; no account-key rotation on errors.
- Discovers read-only MCP schemas, chooses tools, and submits a structured decision.
- Evidence-ledger validation rejects identifiers not returned by allowed MCP tools.
- Scope is intake readiness: product, lot, supermarket, and intelligible complaint.
- Lack of lab results, storage records, or related reports alone is not an intake blocker.
- New runs require fresh importer review. An earlier supermarket review is never copied into
  an approval for a newly generated triage proposal.
- Explicit offline triage simulation remains available through `AGENT_MODE=demo`.

### Traceability without Groq

- `backend/app/agents/traceability.py` no longer imports or invokes the Groq runner.
- Exact SKU, exact product name, or known alias is matched against MCP catalogue results.
- A unique partial search result alone is insufficient for an exact match.
- Product plus manufacturer lot resolves the batch; absent shipments produce an information request.
- Recorded shipments supply recipient IDs, names, quantities, and references. Other retailers
  are returned as excluded evidence. Related reports are retrieved for the same product/lot.
- Results have `execution_mode=rules`, `model=null`, and MCP traces.
- An approved proposal creates retailer inspections; running the stage alone dispatches nothing.

### Escalation without Groq

- `backend/app/agents/escalation.py` no longer imports or invokes the Groq runner.
- Reads current approved trace, batch shipments, distribution totals, human findings, evidence
  metadata, and case timeline through MCP.
- Requires completed checks for every recorded recipient, including a second check inside the
  worker in addition to API prerequisites.
- If any human reports an observed issue, prepares a manufacturer packet for importer review.
- With no observed issue but inconclusive findings, proposes targeted reinspection.
- Otherwise proposes monitoring. Monitoring never creates a manufacturer inbox item.
- Conflicting findings remain visible; checked quantity is not fabricated from shipment quantities.
- No automated safety verdict or recall occurs.

### Persistent human gates

- A run, versioned proposal, and human decision are stored in the database.
- The latest input snapshot must match before approval. Inputs include case identity/information,
  upstream proposal IDs, and escalation's evidence/finding revision.
- Duplicate identical approval requests are idempotent; conflicting retries are rejected.
- The latest approved triage must permit investigation before traceability can start.
- The latest approved trace must match current shipment records before escalation can start.
- Follow-up approval reopens only selected tasks, with previous findings/notes preserved in audit.
- Manufacturer packet creation occurs in the approved proposal transaction. The legacy create
  endpoint cannot bypass approval; it can retrieve an existing escalation.
- Manufacturer responses are organization-scoped. Importer closure/verdict requires response/notes.
- Arbitrary operational status changes cannot substitute for approval.

### UI and diagnostics

- Agent cards show Groq model/turns for LLM results and “Rule-based · MCP records · No LLM” for rules.
- Eligible stages show Ready instead of Locked simply because no run exists yet.
- Backend-provided gates drive run-button availability and explain the exact blocker.
- Changed case information reports that triage must be rerun/reapproved, instead of claiming that
  an already-approved run was never reviewed.
- The save-facts button states that fresh triage is required; final verdict controls appear after
  a manufacturer response.
- Importer sees named supermarket progress, findings, manufacturer response, and audit events.
- Long provider cooldowns surface promptly with retry time; no silent rule-based LLM fallback.

## 3. File ownership map

| Files | Responsibility |
| --- | --- |
| `backend/app/agents/triage.py`, `agentic.py`, `common.py` | Triage routing, bounded LLM execution, validation, quota handling; lower-level LLM contracts remain for tests/history |
| `backend/app/agents/traceability.py` | Active deterministic tracing stage |
| `backend/app/agents/escalation.py` | Active deterministic escalation stage |
| `backend/app/agents/schemas.py` | Structured stage output contracts |
| `backend/app/config.py`, `.env.example` | Triage-only credentials and stage execution mode |
| `backend/app/services/case_workflow.py` | Current approval/input/recipient gates and UI workflow state |
| `backend/app/services/investigation.py`, `workflow.py` | Queue/run/proposal lifecycle and LangGraph human interrupt |
| `backend/app/mcp_server.py`, `services/mcp_client.py` | Read-only MCP evidence and stage allowlists |
| `backend/app/api/cases.py`, `escalations.py`, `reports.py` | Role-scoped mutations and intake/handoff APIs |
| `backend/app/models.py`, `alembic/versions/20261016_0003_approval_inputs.py` | Durable input snapshots and migration |
| `frontend/src/App.tsx`, `api.ts`, `types.ts` | Public/staff screens, execution labels, controls and API contracts |
| `backend/tests/test_rule_stages.py` | No-model rule-stage and recommendation tests |
| `backend/tests/test_agentic.py`, `test_workflow_guards.py` | LLM validation, quota/credential behavior and approval regressions |

## 4. Environment contract

```dotenv
AGENT_MODE=llm
GROQ_MODEL=openai/gpt-oss-20b
GROQ_API_KEY=
GROQ_TRIAGE_API_KEY=
```

Only one populated credential is needed for triage: its dedicated key takes precedence over the
shared key. Traceability and escalation require neither credential and never fall back to one.
The removed `GROQ_TRACEABILITY_API_KEY` and `GROQ_ESCALATION_API_KEY` slots are no longer Settings
fields or active worker inputs. Do not reuse the earlier three-key instructions.

`AGENT_MODE` applies to triage; rules remain active for tracing/escalation in both modes.
Credentials belong in ignored `.env` locally and provider secrets for deployment. Restart after edits.
Keys are not included in results, logs, frontend payloads, or commits.

## 5. Compatibility and data preservation

- Migration `20261016_0003` adds `AgentRun.input_snapshot`; it does not delete workflow records.
- Snapshot upgrade/downgrade/upgrade was checked on disposable SQLite; local upgrade preserved
  record counts before the explicitly requested later database resets.
- Old decisions and LLM results remain historical records, with their original execution metadata.
- Pending results from a different execution mode can be superseded when rerunning the stage.
- Existing approved trace and completed findings can support the new rule-based escalation when
  their input and shipment checks still pass.
- Local database resets were requested test operations, not committed database migrations or seeds.
- Do not reset the user's current database merely to load new code.

## 6. Verification evidence

Local checks after the rule-based switch:

```bash
.venv/bin/ruff check backend --no-cache
.venv/bin/pytest -q
cd frontend && npm run build
```

Results: Ruff passed; **35 backend tests passed**; TypeScript/Vite production build passed.
Tests use synthetic records and scripted LLM responses; they do not consume live Groq quota.
Coverage includes public photo intake, roles, CSV imports, exact lot routing, fresh/stale approvals,
request-information gating, all-retailer prerequisites, monitoring/follow-up behavior, model errors,
long quota cooldowns, triage credentials, and rule-stage operation with model construction forbidden.

Live local verification used the existing fictional case without resetting its history:

- Rule-based traceability read MCP records and returned Retailers A, B, C for lot 38.
- Rule-based escalation completed and saved a manufacturer packet awaiting importer approval.
- No Groq request was needed for either of those worker runs.
- The packet was left unapproved so the user could continue the manufacturer test.

This does not verify production deployment, a real retailer connector, or real contamination.

## 7. Continue testing

Use `DEMO_RUNBOOK.md`. Existing case state may already be at a human checkpoint: review that proposal
instead of rerunning earlier completed stages. Saving new facts requires fresh triage. If all retailer
findings exist, run escalation directly after its prerequisites pass. Approve the packet, log into
the manufacturer's inbox, submit a fictional response, then return as importer for verdict/closure.

## 8. Remaining work and limits

- Alternate Clouds deployment and PostgreSQL persistence/redeploy verification are pending.
- Container smoke check and browser keyboard/viewport verification remain pending.
- Barcode mapping is simulated; OCR/barcode decoding is not implemented.
- Messages are in-app tasks/inboxes; no email, SMS, live ERP or regulator integrations.
- No laboratory connector, autonomous contamination diagnosis, or autonomous recall.
- Monitoring requires a human follow-up; there is no scheduled monitoring worker.
- Background execution is in-process with startup recovery, not a multi-worker queue/lease system.
- Production backups, scale, operational observability, and multi-importer isolation need further work.
