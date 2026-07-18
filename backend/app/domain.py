"""Typed business operations. These are the only database functions exposed to agents."""
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import ApprovalRequest, AuditEvent, Campaign, CampaignTarget, Customer, Investigation, Memory, Order, Product, SupportCase


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
        "lifetime_value": float(customer.lifetime_value), "last_purchase_at": customer.last_purchase_at.isoformat() if customer.last_purchase_at else None,
    })


def get_customer_by_external_id(session: Session, external_id: str) -> dict:
    customer = session.scalar(select(Customer).where(Customer.external_id == external_id))
    if not customer:
        raise ValueError("Customer not found")
    return get_customer_profile(session, customer.id)


def find_churn_risk_customers(session: Session, min_risk: float = 0.65, limit: int = 20) -> dict:
    rows = session.scalars(select(Customer).where(Customer.churn_risk >= min_risk).order_by(Customer.lifetime_value.desc()).limit(limit)).all()
    result = {"customers": [{"id": c.id, "external_id": c.external_id, "segment": c.segment, "risk": c.churn_risk, "ltv": float(c.lifetime_value)} for c in rows]}
    return audit(session, "find_churn_risk_customers", {"min_risk": min_risk, "limit": limit}, result)


def find_eligible_retention_customers(session: Session, limit: int = 20) -> dict:
    blocked = select(CampaignTarget.customer_id).join(Campaign).where(Campaign.status.in_(["draft", "active"]))
    rows = session.scalars(
        select(Customer)
        .where(Customer.segment == "at_risk_high_value", Customer.churn_risk >= 0.65, ~Customer.id.in_(blocked))
        .order_by(Customer.lifetime_value.desc())
        .limit(limit)
    ).all()
    result = {"customers": [{"id": c.id, "external_id": c.external_id, "segment": c.segment, "risk": c.churn_risk, "ltv": float(c.lifetime_value)} for c in rows]}
    return audit(session, "find_eligible_retention_customers", {"limit": limit}, result)


def top_customers_by_lifetime_value(session: Session, limit: int = 5) -> dict:
    rows = session.scalars(select(Customer).order_by(Customer.lifetime_value.desc()).limit(limit)).all()
    return audit(session, "top_customers_by_lifetime_value", {"limit": limit}, {"customers": [{"id": c.id, "external_id": c.external_id, "country": c.country, "lifetime_value": float(c.lifetime_value), "risk": c.churn_risk} for c in rows]})


def find_customers_by_country(session: Session, country: str, limit: int = 20) -> dict:
    rows = session.scalars(select(Customer).where(Customer.country.ilike(country)).order_by(Customer.lifetime_value.desc()).limit(limit)).all()
    return audit(session, "find_customers_by_country", {"country": country, "limit": limit}, {"customers": [{"id": c.id, "external_id": c.external_id, "segment": c.segment, "lifetime_value": float(c.lifetime_value)} for c in rows]})


def get_customer_purchase_history(session: Session, customer_id: int, limit: int = 20) -> dict:
    rows = session.scalars(select(Order).where(Order.customer_id == customer_id).order_by(Order.order_date.desc()).limit(limit)).all()
    return audit(session, "get_customer_purchase_history", {"customer_id": customer_id}, {"orders": [{"invoice": o.invoice_number, "date": str(o.order_date), "total": float(o.total), "status": o.status} for o in rows]})


def get_purchase_history_by_external_id(session: Session, external_id: str, limit: int = 20) -> dict:
    customer = session.scalar(select(Customer).where(Customer.external_id == external_id))
    if not customer:
        raise ValueError("Customer not found")
    history = get_customer_purchase_history(session, customer.id, limit)
    return {"customer": {"id": customer.id, "external_id": customer.external_id, "country": customer.country, "segment": customer.segment, "risk": customer.churn_risk, "lifetime_value": float(customer.lifetime_value)}, **history}


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


def create_campaign_draft(session: Session, name: str, segment: str, offer: str, investigation_id: int | None = None, customer_ids: list[int] | None = None) -> dict:
    selected = customer_ids or []
    already_targeted = set(session.scalars(select(CampaignTarget.customer_id).join(Campaign).where(Campaign.status.in_(["draft", "active"]))).all())
    eligible = list(dict.fromkeys(customer_id for customer_id in selected if customer_id not in already_targeted))
    if selected and not eligible:
        raise ValueError("Every selected customer already belongs to a draft or active campaign")
    campaign = Campaign(name=name, segment=segment, offer=offer, investigation_id=investigation_id)
    session.add(campaign)
    session.flush()
    session.add_all([CampaignTarget(campaign_id=campaign.id, customer_id=customer_id) for customer_id in eligible])
    session.commit()
    return audit(session, "create_campaign_draft", {"name": name, "segment": segment, "offer": offer, "requested_targets": len(selected)}, {"campaign_id": campaign.id, "status": campaign.status, "target_count": len(eligible), "excluded_existing_targets": len(selected) - len(eligible)}, investigation_id)


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
    target_status = "approved" if approved else "rejected"
    for target in session.scalars(select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)).all():
        target.status = target_status
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


def explain_platform(session: Session, question: str = "What does this app do?") -> dict:
    text = question.lower()
    definitions = [
        {"term": "Lifetime value (LTV)", "plain_name": "Total customer spend", "meaning": "The total value of all recorded orders for one customer.", "calculation": "Sum of the customer's order totals.", "example": "£1,056 means the customer has placed orders worth £1,056 in this dataset."},
        {"term": "Churn risk", "plain_name": "Likelihood of not returning", "meaning": "An explainable estimate that a customer may not purchase again soon.", "calculation": "70% of purchase inactivity over 180 days, plus 25% when the customer ordered only once; capped at 95%.", "example": "95% means the customer has been inactive for a long time and/or purchased only once."},
        {"term": "Customer segment", "plain_name": "Customer group", "meaning": "A business label used to group customers with similar value and risk.", "calculation": "At risk + high value requires churn risk of at least 65% and total spend of at least £250.", "example": "at_risk_high_value means valuable customer likely to stop buying; active means the customer does not meet that combined rule."},
    ]
    agents = [
        {"name": "Supervisor", "role": "Understands the request, creates the plan, and chooses which specialists should work."},
        {"name": "Customer Intelligence Agent", "role": "Uses MCP tools to retrieve rankings, profiles, locations, purchase history, risk and customer value."},
        {"name": "Product Intelligence Agent", "role": "Checks product cancellations and performance when churn or campaigns are investigated."},
        {"name": "Memory Agent", "role": "Retrieves previous business rules and learnings stored in PostgreSQL."},
        {"name": "Campaign & Safety Agent", "role": "Selects only eligible customers, prevents duplicate targeting, creates a draft, and requests human approval."},
        {"name": "Response Agent", "role": "Combines agent evidence into a clear answer without changing customer data."},
    ]
    if any(phrase in text for phrase in ("what does this app", "what this app", "what is this app", "how does this app", "what is customerpulse", "explain the app", "explain this app")):
        answer = "CustomerPulse helps a customer-operations manager explore retail data, understand customer value and inactivity risk, investigate churn with specialist agents, and create deduplicated retention campaign drafts that require human approval."
    elif any(word in text for word in ("lifetime", "ltv", "spend", "parameter", "column", "metric", "segment", "churn")):
        answer = "These fields are derived business metrics, not original UCI columns. They turn transaction history into understandable customer value and risk signals."
    elif any(word in text for word in ("multi-agent", "multi agent", "agent", "role")):
        answer = "Multiple specialist agents divide the work: one routes, others collect customer/product/memory evidence, and only the safety-controlled campaign agent may create a draft action."
    elif any(word in text for word in ("campaign", "eligible", "over", "exhaust")):
        answer = "Each campaign selects new eligible high-value customers. Customers already in draft or active campaigns are excluded. When none remain, the agent creates nothing and reports that the eligible pool is exhausted."
    else:
        answer = "CustomerPulse helps a customer-operations manager explore retail data, understand customer value and inactivity risk, investigate churn with specialist agents, and create deduplicated retention campaign drafts that require human approval."
    result = {
        "answer": answer,
        "definitions": definitions,
        "agents": agents,
        "campaign_policy": "Read-only questions never create campaigns. Only an explicit create/draft campaign request can write a campaign, and approval is required before activation. Draft and active targets are excluded from later campaigns; when the eligible pool reaches zero, no campaign is created.",
    }
    return audit(session, "explain_platform", {"question": question}, result)


def dashboard_summary(session: Session) -> dict:
    blocked = select(CampaignTarget.customer_id).join(Campaign).where(Campaign.status.in_(["draft", "active"]))
    return {
        "customers": session.scalar(select(func.count()).select_from(Customer)) or 0,
        "products": session.scalar(select(func.count()).select_from(Product)) or 0,
        "orders": session.scalar(select(func.count()).select_from(Order)) or 0,
        "high_risk_customers": session.scalar(select(func.count()).select_from(Customer).where(Customer.churn_risk >= 0.65)) or 0,
        "high_value_at_risk": session.scalar(select(func.count()).select_from(Customer).where(Customer.segment == "at_risk_high_value")) or 0,
        "eligible_retention_customers": session.scalar(select(func.count()).select_from(Customer).where(Customer.segment == "at_risk_high_value", ~Customer.id.in_(blocked))) or 0,
        "currently_targeted_customers": session.scalar(select(func.count(func.distinct(CampaignTarget.customer_id))).join(Campaign).where(Campaign.status.in_(["draft", "active"]))) or 0,
        "pending_approvals": session.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == "pending")) or 0,
    }
