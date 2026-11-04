# Escalera

Escalera is an importer-owned food batch investigation system. Consumers and retailer food
safety managers report suspected product issues. Three MCP-grounded LangGraph stages triage the
report, trace the exact batch, and prepare manufacturer escalation evidence. Triage uses Groq;
traceability and escalation use database-backed rules without model calls. Humans approve every
handoff and safety decision.

## Backend quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --app-dir backend --reload
```

Open `http://localhost:8000/docs`. Demo data is seeded by default. Accounts use the password in
`DEMO_PASSWORD`:

- `importer@escalera.demo`
- `retailer-a@escalera.demo`
- `retailer-b@escalera.demo`
- `retailer-c@escalera.demo`
- `manufacturer@escalera.demo`

Set `GROQ_TRIAGE_API_KEY` (or the fallback `GROQ_API_KEY`) in ignored `.env` for triage.
`AGENT_MODE=llm` is the default; `AGENT_MODE=demo` selects explicit offline triage simulation.
Traceability and escalation always use deterministic rules and read-only MCP records, without
Groq keys or model calls. Restart after environment changes; never put secrets in `.env.example`.
Triage failures are explicit and never silently switch to rules.

## Use your own records

For a clean local database, choose a new `DATABASE_URL` in ignored `.env` (for example,
`sqlite:///./escalera-local.db`) and set `SEED_DEMO_DATA=false` **before** running migrations.
This leaves the existing `batchbridge.db` and its demo cases untouched. Then run:

```bash
alembic upgrade head
PYTHONPATH=backend python -m app.bootstrap_importer
```

The bootstrap command prompts for the first importer organization, investigator email, and
password. It refuses to create a second importer account. Start the backend and frontend, sign in
as that importer, and open **Data setup**. Create each manufacturer and retailer with its first
staff login. Import the **batch CSV first**, then the **shipment CSV**, using the codes shown on
that page. Templates and row errors are available there. Imported products, lots, and shipments
are stored in the database and used by the MCP-backed traceability stage.

A retailer can then sign in and use **New report** to select an imported product by SKU, enter its
manufacturer lot, and start a suspected-issue case. The importer reviews triage and traceability
before retailer tasks are assigned. Initial staff passwords must be shared privately; the app
does not send email invitations. The public photo flow still uses a simulated barcode for demo
verification; use the retailer report flow for your own imported products.

Changing `SEED_DEMO_DATA` does not remove records already in a database. Keep the demo database
separate from your own-data database.

## Frontend quick start

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`. The production Docker image builds the
responsive React application and serves it from the FastAPI origin.

For a single local URL after installing frontend dependencies:

```bash
cd frontend
npm run build
cd ..
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. Keep the server terminal running; connection refused means no server
is listening. Local testing does not require Docker. See `DEMO_RUNBOOK.md` for the full role flow.

## Verification

```bash
ruff check backend
pytest
```

## Alternate Clouds

Create a PostgreSQL 17 template service and a GitHub application service. Link PostgreSQL to the
application so `DATABASE_URL` is injected. Set the other values from `.env.example`, then follow the
required order: **set variables, rebuild, deploy**.

The container listens on `0.0.0.0:$PORT`. All durable state is stored in PostgreSQL.

## Backend behavior

- Consumers submit reports directly and receive a private tracking token.
- Retailer safety managers can file their own report, review and forward customer cases, add
  evidence, and complete assigned checks.
- Triage, traceability, and escalation agents share one read-only MCP evidence server with explicit
  per-agent tool permissions.
- Groq chooses triage tools and recommendations. Traceability resolves exact product/lot and
  recorded shipments; escalation applies documented rules to human inspection findings.
- Agent cards show execution mode, model, model-turn count, evidence summaries, questions, and MCP
  calls. Rule-based stages are labeled explicitly; historical results retain their execution mode.
- Importer approval creates retailer tasks; no tool or model can create them before that approval.
- Manufacturer escalation requires an approved traceability proposal, completed findings from every assigned retailer, an escalation-agent packet, and a second importer approval.

The interactive OpenAPI contract at `/docs` covers the full API.

## Project documentation

- [`AGENTS.md`](AGENTS.md): project invariants and coding handoff for future agents.
- [`CONTEXT.md`](CONTEXT.md): stable decisions, roles, safety rules, and demo dataset.
- [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md): complete use case, scope, requirements, and success criteria.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): components, trust boundaries, data flow, and deployment shape.
- [`API_REFERENCE.md`](API_REFERENCE.md): endpoint and MCP tool map.
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md): checklist from product scope through submission.
- [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md): detailed completed-work and verification handoff.
- [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md): judge-ready story, checks, and fallback path.
- [`FRONTEND_REFERENCE.md`](FRONTEND_REFERENCE.md): responsive UI direction.
- [`DEPLOYMENT.md`](DEPLOYMENT.md): Alternate Clouds setup and verification.


## Hybrid execution update (2026-10-17)

Only triage uses Groq (`GROQ_TRIAGE_API_KEY`, falling back to `GROQ_API_KEY`).
Traceability and escalation always use deterministic rules and read-only MCP records,
regardless of AGENT_MODE; their dedicated API-key slots were removed. Traceability
requires an exact SKU/name/known alias plus lot and recorded shipments. Escalation
requires every assigned retailer finding; observed issues prepare a manufacturer
packet, inconclusive findings without observed issues propose targeted follow-up,
and otherwise propose monitoring. Every consequential action still requires human
approval. These stages are labeled rule-based in the UI, not LLM-powered.
Existing pending results from another execution mode can be rerun; history remains.
