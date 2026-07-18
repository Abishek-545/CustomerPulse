# CustomerPulse

CustomerPulse is a deployed, autonomous customer-operations platform built with React, FastAPI, PostgreSQL, Groq, LangGraph, and the official Model Context Protocol SDK. It turns retail transactions into explainable customer intelligence, plans multi-step work, calls specialist MCP servers, observes every result, replans safely, and performs controlled CRUD.

## Business workflows

- Customer intelligence: rankings, profiles, geography, purchase history, value and inactivity-risk analysis.
- Retention campaigns: deduplicated customer selection, campaign draft creation, manager approval, email delivery and campaign outcomes.
- Customer-care triage: creates deduplicated internal support cases for high-risk customers.
- Product recovery: identifies elevated cancellation signals and creates operational recovery tasks.
- Closed-loop learning: completed campaign conversion and uplift are stored as long-term business memory.
- Product guidance: a Knowledge Agent explains the application, metrics, safety rules and agent roles.

## Autonomous LangGraph loop

```text
Goal -> Supervisor/Planner -> Specialist Executor -> Observer/Replanner
                              ^                         |
                              |---- continue/revise ----|
                                                        -> Response/Learning
```

Groq may choose the smallest plan from a constrained action catalog. Deterministic intent guards prevent a read-only request from gaining write actions. After every tool result, the observer can continue, remove unjustified dependent actions, or finish. A configurable maximum-step limit prevents runaway loops.

Graph checkpoints use PostgreSQL in production (`PostgresSaver`) and an in-memory saver only for SQLite tests. This provides durable thread state and restart recovery.

## Real MCP architecture

Six FastMCP servers are mounted through Streamable HTTP:

| Server | Responsibility |
| --- | --- |
| Customer | Profiles, purchases, rankings, geography and risk |
| Product | Product performance and cancellation signals |
| Campaign | Drafts, approval policy, delivery status and outcomes |
| Memory | Long-term business learning |
| Knowledge | Product guide, glossary and agent explanations |
| Operations | Support cases and product-recovery tasks |

The production agent gateway uses the official MCP client lifecycle and performs `tools/list`, `resources/list`, `prompts/list`, and `tools/call`. The Quality & MCP screen displays live-discovered capabilities. A direct allowlisted adapter remains available only for offline tests and degraded local development.

## Human approval and email

Only an explicit campaign request can create a draft. Draft and active customer IDs cannot be selected by another campaign. Approval activates the campaign and creates one delivery per campaign target.

Until real consented customer addresses are available, every target maps to the safety inbox `temp66642@gmail.com`.

- `EMAIL_MODE=log`: creates simulated delivery records without sending externally.
- `EMAIL_MODE=smtp`: sends real messages and records sent/failed status.

The manager UI reports sent, simulated and failed totals. Configure `SMTP_USERNAME`, `SMTP_PASSWORD` (a Gmail app password), and `SMTP_FROM_EMAIL` in Render before enabling SMTP mode.

## Evaluation

The versioned 40-case regression dataset measures:

- intent accuracy;
- parameter extraction;
- unsafe-action prevention;
- expected agent trajectory validity.

Evaluations run from the Quality & MCP screen and are stored in PostgreSQL. The same suite is exercised in CI alongside domain, campaign, email, idempotency and outcome tests.

## Data and database CRUD

The project uses the UCI Online Retail dataset and persists customers, products, invoices, campaign targets, approvals, email deliveries, outcomes, support cases, operational tasks, agent steps, memories, evaluations and audit events.

The importer loads 50,000 source rows by default to remain within small Render instances. Set `RETAIL_IMPORT_LIMIT=0` only when the service has enough memory.

## Quick start

1. Copy `.env.example` to `.env` and set `GROQ_API_KEY`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`.
4. Optionally import UCI data:

```bash
python -m app.import_retail_data
```

The application creates additive tables automatically on startup. Production schema changes should be managed with Alembic before making destructive column changes.

## Safety scope

- Read-only questions cannot create campaigns, support cases or recovery tasks.
- Campaigns require explicit creation language and human approval.
- Email delivery is idempotent per campaign target.
- Campaign and operations writes are deduplicated.
- Customer-row locks reduce competing campaign selection races.
- Every agent tool call and autonomous decision is auditable.
- Authentication is intentionally omitted from the public portfolio demo so interviewers can inspect the complete workflow.
