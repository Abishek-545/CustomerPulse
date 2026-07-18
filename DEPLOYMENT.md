# Deployment

## Render services

The repository contains a Docker backend and frontend. The backend also hosts six isolated FastMCP Streamable HTTP applications under `/mcp/{server}/mcp`, so a separate paid MCP service is not required for the portfolio deployment.

Required backend variables:

```text
DATABASE_URL=<Render PostgreSQL external or internal URL>
GROQ_API_KEY=<Groq API key>
BACKEND_CORS_ORIGINS=https://customerpulse-ui.onrender.com
MCP_TRANSPORT=streamable-http
MCP_BASE_URL=https://customerpulse-api-jhsk.onrender.com
CHECKPOINT_BACKEND=postgres
MAX_AGENT_STEPS=8
DEMO_RECIPIENT_EMAIL=temp66642@gmail.com
```

Render normally exposes `RENDER_EXTERNAL_URL`, so `MCP_BASE_URL` is optional when `MCP_TRANSPORT=auto`.

## Enable real email

Keep `EMAIL_MODE=log` while testing. To send real approved campaign messages to the demo inbox, add:

```text
EMAIL_MODE=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<sender Gmail address>
SMTP_PASSWORD=<Gmail app password, not the normal password>
SMTP_FROM_EMAIL=<sender Gmail address>
SMTP_FROM_NAME=CustomerPulse Retention Team
```

Approval will then send one individualized message for every campaign target and record the provider result. All targets intentionally resolve to the single demo inbox.

## Production notes

- PostgreSQL creates both application tables and LangGraph checkpoint tables.
- MCP capability discovery is cached for five minutes.
- Use an internal MCP bearer token (`MCP_INTERNAL_TOKEN`) when the service is not a public portfolio demo.
- Add Alembic before destructive schema evolution.
- Upgrade the Render instance if concurrent agent traffic exceeds the free instance memory limit.
