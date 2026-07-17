from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.domain import create_campaign_draft, decide_campaign_approval, find_churn_risk_customers, request_campaign_approval
from app.models import Customer


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
