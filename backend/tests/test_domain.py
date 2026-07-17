from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.domain import create_campaign_draft, decide_campaign_approval, find_churn_risk_customers, find_eligible_retention_customers, request_campaign_approval
from app.models import CampaignTarget, Customer
from app.reasoner import route_goal


def test_campaign_requires_approval_before_activation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Customer(external_id="test-customer", country="UK", churn_risk=0.9, lifetime_value=100))
    session.commit()
    campaign = create_campaign_draft(session, "Retention", "at_risk_high_value", "10% off")
    approval = request_campaign_approval(session, campaign["campaign_id"], "Policy gate")
    result = decide_campaign_approval(session, approval["approval_id"], True, "tester")
    assert result["campaign_status"] == "active"
    assert find_churn_risk_customers(session)["customers"][0]["external_id"] == "test-customer"


def test_read_only_customer_query_never_routes_to_campaign():
    route = route_goal("show top 5 customers")
    assert route.intent == "top_customers"
    assert route.limit == 5
    assert route_goal("Show customer 16246 details").customer_external_id == "16246"


def test_campaign_targets_are_saved_and_not_retargeted():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customer = Customer(external_id="16244", country="UK", segment="at_risk_high_value", churn_risk=0.95, lifetime_value=1000)
    session.add(customer)
    session.commit()
    first = create_campaign_draft(session, "Win back", "at_risk_high_value", "10% off", customer_ids=[customer.id])
    assert first["target_count"] == 1
    assert session.query(CampaignTarget).count() == 1
    assert find_eligible_retention_customers(session)["customers"] == []
    try:
        create_campaign_draft(session, "Duplicate", "at_risk_high_value", "10% off", customer_ids=[customer.id])
        assert False, "duplicate target should have been rejected"
    except ValueError:
        pass
