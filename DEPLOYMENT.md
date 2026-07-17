# Deployment

## Database

Create a free Neon PostgreSQL project and set `DATABASE_URL` to its SQLAlchemy form:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require
```

On first startup the API creates its tables and inserts demo data. Run the UCI importer once from a local environment or a one-off worker to load the full transaction dataset.

## Render + Vercel

1. Deploy `backend/` as a Docker web service on Render. Set `DATABASE_URL` and `BACKEND_CORS_ORIGINS`.
2. Deploy `frontend/` on Vercel. Set `VITE_API_URL` to the deployed API URL.
3. Update the backend CORS origin to the Vercel URL.

## Required production hardening

- Add authentication and organization-scoped row-level access.
- Replace the demo manager identity with the authenticated user.
- Use a durable LangGraph PostgreSQL checkpointer for concurrent workers.
- Deploy each MCP server behind Streamable HTTP with service authentication.
- Add rate limits, telemetry, automated agent evaluations, and database migrations.
