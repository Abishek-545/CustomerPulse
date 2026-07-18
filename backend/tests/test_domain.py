from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.domain import create_campaign_draft, create_support_cases_for_customers, dashboard_summary, decide_campaign_approval, explain_platform, find_churn_risk_customers, find_eligible_retention_customers, list_operational_tasks, request_campaign_approval, simulate_campaign_outcome
from app.evaluations import run_offline_evaluations
from app.models import CampaignTarget, Customer, EmailDelivery, Memory
from app.reasoner import route_goal
from app.config import settings
from app.schema_migrations import migrate_customer_email


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
    assert route_goal("What does this app do?").intent == "help"
    assert route_goal("What is the role of multi agent here?").intent == "help"
    assert route_goal("What does lifetime value mean?").intent == "help"
    assert route_goal("What is segment?").intent == "help"
    assert route_goal("Create support cases for 6 risky customers").intent == "support_triage"
    assert route_goal("Create product recovery tasks for 5 products").intent == "product_recovery"
    assert route_goal("Campaign 12 conversion result").campaign_id == 12


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
    summary = dashboard_summary(session)
    assert summary["eligible_retention_customers"] == 0
    assert summary["currently_targeted_customers"] == 1
    try:
        create_campaign_draft(session, "Duplicate", "at_risk_high_value", "10% off", customer_ids=[customer.id])
        assert False, "duplicate target should have been rejected"
    except ValueError:
        pass


def test_platform_help_explains_metrics_agents_and_campaign_capacity():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    result = explain_platform(session, "What does this app do and what is lifetime value?")
    assert "retention" in result["answer"].lower()
    assert {item["term"] for item in result["definitions"]} == {"Lifetime value (LTV)", "Churn risk", "Customer segment"}
    assert any(item["name"] == "Supervisor" for item in result["agents"])
    assert "eligible pool reaches zero" in result["campaign_policy"]


def test_support_cases_are_visible_in_operations_backlog():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customer = Customer(external_id="support-101", country="UK", segment="active", churn_risk=0.8, lifetime_value=90)
    session.add(customer)
    session.commit()
    create_support_cases_for_customers(session, [customer.id], "Proactive churn-risk review")
    tasks = list_operational_tasks(session)["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["type"] == "support_followup"
    assert tasks[0]["payload"]["customer_external_id"] == "support-101"


def test_customer_email_migration_backfills_existing_rows():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, external_id VARCHAR(64))"))
        connection.execute(text("INSERT INTO customers (external_id) VALUES ('legacy-1'), ('legacy-2')"))
    migrate_customer_email(engine)
    with engine.connect() as connection:
        emails = connection.execute(text("SELECT email FROM customers ORDER BY id")).scalars().all()
    assert emails == ["temp66642@gmail.com", "temp66642@gmail.com"]


def test_approval_creates_idempotent_demo_email_and_outcome_learning():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    settings.email_mode = "log"
    customer = Customer(external_id="email-demo", country="UK", segment="at_risk_high_value", churn_risk=0.9, lifetime_value=500)
    session.add(customer)
    session.commit()
    draft = create_campaign_draft(session, "Email campaign", "at_risk_high_value", "10% discount", customer_ids=[customer.id])
    approval = request_campaign_approval(session, draft["campaign_id"], "Manager gate")
    decision = decide_campaign_approval(session, approval["approval_id"], True, "tester")
    assert decision["email_delivery"]["simulated"] == 1
    assert session.query(EmailDelivery).one().recipient == "temp66642@gmail.com"
    outcome = simulate_campaign_outcome(session, draft["campaign_id"])
    assert outcome["delivered"] == 1
    assert outcome["status"] == "complete"
    assert session.query(Memory).filter_by(category="campaign_outcome").count() == 1


def test_40_case_agent_evaluation_suite_is_green():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    result = run_offline_evaluations(session)
    assert result["scores"]["cases"] == 40
    assert result["scores"]["intent_accuracy"] == 1.0
    assert result["scores"]["unsafe_action_prevention"] == 1.0
