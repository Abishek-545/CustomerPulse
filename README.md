# CustomerPulse

CustomerPulse is an MCP-native, human-supervised customer and product operations agent. It imports real retail transactions into PostgreSQL, investigates goals such as churn reduction or product decline, uses LangGraph to plan and revise work, and performs controlled CRUD through domain MCP tools.

## What it demonstrates

- Real relational data: customers, products, orders, campaigns, support cases, approvals and audit events.
- Agent loop: plan -> investigate -> observe -> re-plan -> propose -> approve -> act -> learn.
- MCP architecture: distinct Customer, Product, Campaign and Memory servers expose tools, resources and prompts.
- Durable agent state: LangGraph PostgreSQL checkpoints plus long-term business memories.
- Safe actions: the agent creates drafts only; a person must approve before a campaign is activated.

## Quick start

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`.
4. Run the included UCI importer from the backend container if you want the full public dataset:

```bash
python -m app.import_retail_data
```

The app starts with a small safe seed dataset, so it works without downloading data. The importer uses UCI's Online Retail public dataset (541,909 transaction records).

## Architecture

```text
React dashboard -> FastAPI -> LangGraph coordinator -> MCP domain servers -> PostgreSQL
                                         |                    |
                                  checkpoints/memory       safe CRUD tools
```

The backend calls the same typed domain functions used by the MCP servers. This keeps local development simple while preserving the MCP boundary for remote deployment. Set `MCP_TRANSPORT=streamable-http` when deploying servers independently.

## Safety

CustomerPulse is a demonstration system. No email, discount, or payment is sent externally. Campaign activation is simulated and requires a human approval record.

## Project structure

```text
backend/     FastAPI, SQLAlchemy, LangGraph, MCP servers, data import
frontend/    React + TypeScript dashboard
docker-compose.yml
```
