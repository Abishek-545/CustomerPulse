# CustomerPulse

CustomerPulse is an MCP-native, human-supervised multi-agent customer operations platform. It imports real retail transactions into PostgreSQL, routes natural-language requests to specialist LangGraph agents, and performs controlled CRUD through domain MCP tools.

## What it demonstrates

- Real relational data: customers, products, orders, campaigns, support cases, approvals and audit events.
- Multi-agent workflow: Supervisor -> Customer Intelligence -> Product Intelligence -> Memory -> Campaign/Safety -> Response.
- MCP architecture: distinct Customer, Product, Campaign and Memory servers expose tools, resources and prompts.
- Intent-safe routing: rankings, profiles, geography, purchase history and churn analysis are read-only; only explicit campaign requests can create data.
- Long-term memory: business learnings are stored in PostgreSQL and retrieved through the Memory MCP server.
- Safe actions: campaigns store exact customer targets, exclude customers already targeted by draft/active campaigns, and require human approval.

## Quick start

1. Copy `.env.example` to `.env` and set `GROQ_API_KEY`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`.
4. Run the included UCI importer from the backend container if you want the full public dataset:

```bash
python -m app.import_retail_data
```

The app starts with a small safe seed dataset, so it works without downloading data. The importer uses UCI's Online Retail public dataset (541,909 transaction records). It imports 50,000 rows by default to fit Render's 256 MB service; set `RETAIL_IMPORT_LIMIT=0` only on an instance with at least 512 MB RAM.

## Architecture

```text
React workspace -> FastAPI -> LangGraph supervisor -> specialist agents
                                                    -> MCP domain servers -> PostgreSQL
                                                       tools/resources/prompts
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
