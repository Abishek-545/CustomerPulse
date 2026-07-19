from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .db import Base, engine, get_session
from .seed import seed
from .graph import run_investigation
from . import domain
from .models import AgentRunStep, ApprovalRequest, AuditEvent, Campaign, CampaignOutcome, CampaignTarget, Customer, EmailDelivery, EvaluationRun, Investigation, OperationalTask, Product
from .config import settings
from .mcp_client import mcp_client
from .mcp_servers import SERVERS
from .evaluations import list_evaluation_runs, run_offline_evaluations
from .schema_migrations import migrate_customer_email, migrate_customer_segments


MCP_SERVERS = {name: factory() for name, factory in SERVERS.items()}


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    migrate_customer_email(engine)
    with next(get_session()) as session:
        seed(session)
    migrate_customer_segments(engine)
    async with AsyncExitStack() as stack:
        for server in MCP_SERVERS.values():
            await stack.enter_async_context(server.session_manager.run())
        yield


app = FastAPI(title="CustomerPulse API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.backend_cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for server_name, server in MCP_SERVERS.items():
    app.mount(f"/mcp/{server_name}", server.streamable_http_app())


@app.middleware("http")
async def protect_internal_mcp(request: Request, call_next):
    if request.url.path.startswith("/mcp/") and settings.mcp_internal_token:
        if request.headers.get("authorization") != f"Bearer {settings.mcp_internal_token}":
            return JSONResponse(status_code=401, content={"detail": "Invalid MCP service token"})
    return await call_next(request)


class InvestigationRequest(BaseModel):
    goal: str = Field(min_length=10, max_length=1000)


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = Field(default="demo-manager", min_length=2, max_length=120)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard(session: Session = Depends(get_session)):
    return domain.dashboard_summary(session)


@app.get("/api/customers")
def customers(limit: int = 50, session: Session = Depends(get_session)):
    rows = session.scalars(select(Customer).order_by(Customer.churn_risk.desc()).limit(limit)).all()
    return [{"id": c.id, "external_id": c.external_id, "email": c.email, "country": c.country, "segment": c.segment, "churn_risk": c.churn_risk, "lifetime_value": float(c.lifetime_value), "last_purchase_at": c.last_purchase_at} for c in rows]


@app.get("/api/customers/{external_id}")
def customer_detail(external_id: str, session: Session = Depends(get_session)):
    try:
        return domain.get_customer_by_external_id(session, external_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/customers/{external_id}/purchases")
def customer_purchases(external_id: str, limit: int = 20, session: Session = Depends(get_session)):
    try:
        return domain.get_purchase_history_by_external_id(session, external_id, limit)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/products")
def products(session: Session = Depends(get_session)):
    rows = session.scalars(select(Product).order_by(Product.sales_trend.asc())).all()
    return [{"id": p.id, "sku": p.external_sku, "name": p.name, "unit_price": float(p.unit_price), "cancellation_rate": p.cancellation_rate, "sales_trend": p.sales_trend} for p in rows]


@app.post("/api/investigations")
def create_investigation(payload: InvestigationRequest):
    return run_investigation(payload.goal)


@app.get("/api/investigations")
def investigations(session: Session = Depends(get_session)):
    rows = session.scalars(select(Investigation).order_by(Investigation.created_at.desc()).limit(30)).all()
    return [{"id": item.id, "goal": item.goal, "status": item.status, "plan": item.plan, "findings": item.findings, "created_at": item.created_at} for item in rows]


@app.get("/api/approvals")
def approvals(session: Session = Depends(get_session)):
    rows = session.execute(
        select(ApprovalRequest, Campaign)
        .join(Campaign, Campaign.id == ApprovalRequest.campaign_id)
        .order_by(ApprovalRequest.id.desc())
    ).all()
    return [{
        "id": request.id,
        "campaign_id": request.campaign_id,
        "campaign_name": campaign.name,
        "campaign_offer": campaign.offer,
        "campaign_status": campaign.status,
        "reason": request.reason,
        "status": request.status,
        "decided_by": request.decided_by,
        "target_count": session.scalar(select(func.count()).select_from(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)) or 0,
    } for request, campaign in rows]


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval(approval_id: int, payload: ApprovalDecision, session: Session = Depends(get_session)):
    try:
        return domain.decide_campaign_approval(session, approval_id, payload.approved, payload.decided_by)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/mcp/capabilities")
def mcp_capabilities():
    try:
        return mcp_client.discover()
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP discovery failed: {error}") from error


@app.get("/api/campaigns")
def campaigns(session: Session = Depends(get_session)):
    rows = session.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    result = []
    for item in rows:
        outcome = session.scalar(select(CampaignOutcome).where(CampaignOutcome.campaign_id == item.id))
        delivery_counts = dict(session.execute(select(EmailDelivery.status, func.count()).where(EmailDelivery.campaign_id == item.id).group_by(EmailDelivery.status)).all())
        result.append({"id": item.id, "name": item.name, "segment": item.segment, "offer": item.offer, "status": item.status, "investigation_id": item.investigation_id, "target_count": session.scalar(select(func.count()).select_from(CampaignTarget).where(CampaignTarget.campaign_id == item.id)) or 0, "delivery": {"sent": delivery_counts.get("sent", 0), "simulated": delivery_counts.get("simulated", 0), "failed": delivery_counts.get("failed", 0)}, "outcome": None if not outcome else {"delivered": outcome.delivered, "opened": outcome.opened, "clicked": outcome.clicked, "converted": outcome.converted, "revenue": float(outcome.attributed_revenue), "uplift": outcome.uplift, "status": outcome.status}})
    return result


@app.get("/api/campaigns/{campaign_id}/targets")
def campaign_targets(campaign_id: int, session: Session = Depends(get_session)):
    rows = session.execute(select(CampaignTarget, Customer).join(Customer, Customer.id == CampaignTarget.customer_id).where(CampaignTarget.campaign_id == campaign_id)).all()
    return [{"customer_id": customer.id, "external_id": customer.external_id, "segment": customer.segment, "risk": customer.churn_risk, "lifetime_value": float(customer.lifetime_value), "target_status": target.status} for target, customer in rows]


@app.get("/api/campaigns/{campaign_id}/deliveries")
def campaign_deliveries(campaign_id: int, session: Session = Depends(get_session)):
    return domain.campaign_delivery_status(session, campaign_id)


@app.post("/api/campaigns/{campaign_id}/deliver")
def campaign_retry_delivery(campaign_id: int, session: Session = Depends(get_session)):
    try:
        return domain.retry_campaign_delivery(session, campaign_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/campaigns/{campaign_id}/simulate-outcome")
def campaign_simulate_outcome(campaign_id: int, session: Session = Depends(get_session)):
    try:
        return domain.simulate_campaign_outcome(session, campaign_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/operational-tasks")
def operational_tasks(session: Session = Depends(get_session)):
    return domain.list_operational_tasks(session, 100)["tasks"]


@app.get("/api/investigations/{investigation_id}/steps")
def investigation_steps(investigation_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(AgentRunStep).where(AgentRunStep.investigation_id == investigation_id).order_by(AgentRunStep.sequence)).all()
    return [{"id": row.id, "sequence": row.sequence, "agent": row.agent, "action": row.action, "tool": row.tool_name, "status": row.status, "reasoning": row.reasoning, "input": row.input_data, "output": row.output_data, "created_at": row.created_at} for row in rows]


@app.get("/api/audit-events")
def audit_events(session: Session = Depends(get_session)):
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100)).all()
    return [{"id": item.id, "tool": item.tool, "input": item.input_data, "output": item.output_data, "created_at": item.created_at} for item in rows]


@app.get("/api/evaluations")
def evaluations(session: Session = Depends(get_session)):
    return list_evaluation_runs(session)


@app.post("/api/evaluations/run")
def run_evaluation_suite(session: Session = Depends(get_session)):
    return run_offline_evaluations(session)
