from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, get_session
from .seed import seed
from .graph import run_investigation
from . import domain
from .models import ApprovalRequest, AuditEvent, Campaign, Customer, Investigation, Product
from .config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with next(get_session()) as session:
        seed(session)
    yield


app = FastAPI(title="CustomerPulse API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.backend_cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


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
    return [{"id": c.id, "external_id": c.external_id, "country": c.country, "segment": c.segment, "churn_risk": c.churn_risk, "lifetime_value": float(c.lifetime_value), "last_purchase_at": c.last_purchase_at} for c in rows]


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
    } for request, campaign in rows]


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval(approval_id: int, payload: ApprovalDecision, session: Session = Depends(get_session)):
    try:
        return domain.decide_campaign_approval(session, approval_id, payload.approved, payload.decided_by)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/campaigns")
def campaigns(session: Session = Depends(get_session)):
    rows = session.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    return [{"id": item.id, "name": item.name, "segment": item.segment, "offer": item.offer, "status": item.status, "investigation_id": item.investigation_id} for item in rows]


@app.get("/api/audit-events")
def audit_events(session: Session = Depends(get_session)):
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100)).all()
    return [{"id": item.id, "tool": item.tool, "input": item.input_data, "output": item.output_data, "created_at": item.created_at} for item in rows]
