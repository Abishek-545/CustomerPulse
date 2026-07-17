"""Typed business operations. These are the only database functions exposed to agents."""
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import ApprovalRequest, AuditEvent, Campaign, Customer, Investigation, Memory, Order, Product, SupportCase


def audit(session: Session, tool: str, inputs: dict, output: dict, investigation_id: int | None = None) -> dict:
    session.add(AuditEvent(investigation_id=investigation_id, tool=tool, input_data=inputs, output_data=output))
    session.commit()
    return output


def get_customer_profile(session: Session, customer_id: int) -> dict:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError("Customer not found")
    return audit(session, "get_customer_profile", {"customer_id": customer_id}, {
        "id": customer.id, "external_id": customer.external_id, "country": customer.country,
        "segment": customer.segment, "churn_risk": customer.churn_risk,
        "lifetime_value": float(customer.lifetime_value), "last_purchase_at": str(customer.last_purchase_at),
    })


def find_churn_risk_customers(session: Session, min_risk: float = 0.65, limit: int = 20) -> dict:
    rows = session.scalars(select(Customer).where(Customer.churn_risk >= min_risk).order_by(Customer.lifetime_value.desc()).limit(limit)).all()
    result = {"customers": [{"id": c.id, "external_id": c.external_id, "segment": c.segment, "risk": c.churn_risk, "ltv": float(c.lifetime_value)} for c in rows]}
    return audit(session, "find_churn_risk_customers", {"min_risk": min_risk, "limit": limit}, result)


def assign_customer_segment(session: Session, customer_id: int, segment: str) -> dict:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise ValueError("Customer not found")
    old = customer.segment
    customer.segment = segment
    session.commit()
    return audit(session, "assign_customer_segment", {"customer_id": customer_id, "segment": segment}, {"id": customer_id, "old_segment": old, "segment": segment})


def get_product_performance(session: Session, limit: int = 10) -> dict:
    rows = session.scalars(select(Product).order_by(Product.sales_trend.asc()).limit(limit)).all()
    result = {"products": [{"id": p.id, "sku": p.external_sku, "name": p.name, "cancellation_rate": p.cancellation_rate, "sales_trend": p.sales_trend} for p in rows]}
    return audit(session, "get_product_performance", {"limit": limit}, result)


def find_high_cancellation_products(session: Session, threshold: float = 0.10, limit: int = 10) -> dict:
    rows = session.scalars(select(Product).where(Product.cancellation_rate >= threshold).order_by(Product.cancellation_rate.desc()).limit(limit)).all()
    result = {"products": [{"id": p.id, "sku": p.external_sku, "name": p.name, "cancellation_rate": p.cancellation_rate} for p in rows]}
    return audit(session, "find_high_cancellation_products", {"threshold": threshold, "limit": limit}, result)


def create_campaign_draft(session: Session, name: str, segment: str, offer: str, investigation_id: int | None = None) -> dict:
    campaign = Campaign(name=name, segment=segment, offer=offer, investigation_id=investigation_id)
    session.add(campaign)
    session.commit()
    return audit(session, "create_campaign_draft", {"name": name, "segment": segment, "offer": offer}, {"campaign_id": campaign.id, "status": campaign.status}, investigation_id)


def request_campaign_approval(session: Session, campaign_id: int, reason: str) -> dict:
    campaign = session.get(Campaign, campaign_id)
    if not campaign or campaign.status != "draft":
        raise ValueError("Only an existing draft campaign can be submitted")
    request = ApprovalRequest(campaign_id=campaign_id, reason=reason)
    session.add(request)
    session.commit()
    return audit(session, "request_campaign_approval", {"campaign_id": campaign_id}, {"approval_id": request.id, "status": request.status})


def decide_campaign_approval(session: Session, approval_id: int, approved: bool, decided_by: str) -> dict:
    request = session.get(ApprovalRequest, approval_id)
    if not request or request.status != "pending":
        raise ValueError("Approval request is unavailable")
    request.status = "approved" if approved else "rejected"
    request.decided_by, request.decided_at = decided_by, datetime.utcnow()
    campaign = session.get(Campaign, request.campaign_id)
    campaign.status = "active" if approved else "rejected"
    session.commit()
    return audit(session, "decide_campaign_approval", {"approval_id": approval_id, "approved": approved}, {"campaign_id": campaign.id, "campaign_status": campaign.status})


def create_support_case(session: Session, customer_id: int, title: str, priority: str = "normal") -> dict:
    case = SupportCase(customer_id=customer_id, title=title, priority=priority)
    session.add(case)
    session.commit()
    return audit(session, "create_support_case", {"customer_id": customer_id, "title": title}, {"case_id": case.id, "status": case.status})


def search_memories(session: Session, query: str, limit: int = 5) -> dict:
    rows = session.scalars(select(Memory).where(Memory.content.ilike(f"%{query}%")).order_by(Memory.confidence.desc()).limit(limit)).all()
    result = {"memories": [{"id": m.id, "content": m.content, "confidence": m.confidence} for m in rows]}
    return audit(session, "search_memories", {"query": query}, result)


def save_business_learning(session: Session, category: str, content: str, confidence: float = 0.75) -> dict:
    memory = Memory(category=category, content=content, confidence=confidence)
    session.add(memory)
    session.commit()
    return audit(session, "save_business_learning", {"category": category}, {"memory_id": memory.id})


def dashboard_summary(session: Session) -> dict:
    return {
        "customers": session.scalar(select(func.count()).select_from(Customer)) or 0,
        "products": session.scalar(select(func.count()).select_from(Product)) or 0,
        "orders": session.scalar(select(func.count()).select_from(Order)) or 0,
        "high_risk_customers": session.scalar(select(func.count()).select_from(Customer).where(Customer.churn_risk >= 0.65)) or 0,
        "pending_approvals": session.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == "pending")) or 0,
    }
