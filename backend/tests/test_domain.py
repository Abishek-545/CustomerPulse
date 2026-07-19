from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.domain import analyze_product_portfolio, create_campaign_draft, create_product_recovery_tasks, create_support_cases_for_customers, dashboard_summary, decide_campaign_approval, explain_platform, find_churn_risk_customers, find_customers_by_minimum_value, find_eligible_retention_customers, find_frequent_cancellers, find_high_cancellation_products, list_campaign_targets, list_operational_tasks, request_campaign_approval, retry_campaign_delivery, simulate_campaign_outcome, update_operational_task_status
from app.evaluations import run_offline_evaluations
from app.models import CampaignTarget, Customer, EmailDelivery, Memory, Order, Product
from app.planner import TEMPLATES, normalize_actions
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
    assert route_goal("Show customers whose lifetime value is over 5000").intent == "value_customers"
    assert route_goal("Show 20 customers with most cancelled orders").intent == "cancellation_customers"
    assert route_goal("Create a feedback email campaign for 10 customers with cancelled orders").intent == "feedback_campaign"
    assert route_goal("Show low-value products with most cancellations").intent == "product_portfolio"


def test_customer_cancellation_value_and_product_portfolio_tools():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customer = Customer(external_id="cancel-1", country="France", segment="at_risk_lower_value", churn_risk=0.95, lifetime_value=6000)
    products = [Product(external_sku="low", name="Low", unit_price=5, cancellation_rate=.8), Product(external_sku="high", name="High", unit_price=100, cancellation_rate=.01)]
    session.add_all([customer, *products]); session.flush()
    session.add_all([Order(invoice_number="C-1", customer_id=customer.id, order_date=datetime.utcnow(), status="cancelled", total=-20), Order(invoice_number="C-2", customer_id=customer.id, order_date=datetime.utcnow(), status="cancelled", total=-30), Order(invoice_number="3", customer_id=customer.id, order_date=datetime.utcnow(), status="completed", total=50)])
    session.commit()
    cancellation = find_frequent_cancellers(session, limit=10)["customers"][0]
    assert cancellation["cancelled_orders"] == 2
    assert cancellation["cancellation_rate"] == 2 / 3
    assert find_customers_by_minimum_value(session, 5000)["customers"][0]["external_id"] == "cancel-1"
    portfolio = analyze_product_portfolio(session, 5)
    assert portfolio["most_cancelled_low_value"][0]["sku"] == "low"
    assert portfolio["high_value_low_cancellation"][0]["sku"] == "high"


def test_campaign_deduplication_is_scoped_by_business_purpose():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customer = Customer(external_id="multi-purpose", country="UK", segment="at_risk_high_value", churn_risk=.9, lifetime_value=500)
    session.add(customer); session.commit()
    create_campaign_draft(session, "Retention", "at_risk_high_value", "10%", customer_ids=[customer.id])
    feedback = create_campaign_draft(session, "Feedback", "frequent_cancellers", "Tell us why", customer_ids=[customer.id])
    assert feedback["target_count"] == 1


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
    assert {item["term"] for item in result["definitions"]} == {"Lifetime value (LTV)", "Inactivity risk score", "Customer segment"}
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
    result = update_operational_task_status(session, tasks[0]["id"], "completed")
    assert result["previous_status"] == "open"
    assert list_operational_tasks(session)["tasks"][0]["status"] == "completed"


def test_feedback_campaign_targets_include_cancellation_evidence():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customer = Customer(external_id="feedback-1", country="France", segment="at_risk_lower_value", churn_risk=.8, lifetime_value=50)
    session.add(customer); session.flush()
    session.add_all([
        Order(invoice_number="C-10", customer_id=customer.id, order_date=datetime.utcnow(), status="cancelled", total=-30),
        Order(invoice_number="11", customer_id=customer.id, order_date=datetime.utcnow(), status="completed", total=50),
    ])
    session.commit()
    campaign = create_campaign_draft(session, "Cancellation feedback", "frequent_cancellers", "Share feedback", customer_ids=[customer.id])
    target = list_campaign_targets(session, campaign["campaign_id"])[0]
    assert target["country"] == "France"
    assert target["cancelled_orders"] == 1
    assert target["total_orders"] == 2
    assert target["cancellation_rate"] == .5
    assert target["cancelled_value"] == 30


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
    repeated = decide_campaign_approval(session, approval["approval_id"], True, "tester")
    assert repeated["idempotent"] is True
    assert repeated["email_delivery"]["simulated"] == 1
    assert session.query(EmailDelivery).count() == 1
    outcome = simulate_campaign_outcome(session, draft["campaign_id"])
    assert outcome["delivered"] == 1
    assert outcome["status"] == "complete"
    assert session.query(Memory).filter_by(category="campaign_outcome").count() == 1


def test_dependency_sensitive_llm_plan_is_normalized():
    route = route_goal("Create a retention campaign for 10 high-value customers")
    assert normalize_actions(route, ["top_customers", "campaign_draft"]) == TEMPLATES["retention_campaign"]


def test_support_and_product_workflows_select_the_next_unhandled_records():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customers = [Customer(external_id=f"risk-{index}", country="UK", churn_risk=0.9, lifetime_value=500-index) for index in range(3)]
    products = [Product(external_sku=f"sku-{index}", name=f"Product {index}", cancellation_rate=0.5-index/10, sales_trend=-0.2) for index in range(3)]
    session.add_all(customers + products)
    session.commit()
    create_support_cases_for_customers(session, [customers[0].id], "Proactive high-risk customer review")
    create_product_recovery_tasks(session, [products[0].id])
    next_customers = find_churn_risk_customers(session, limit=10, exclude_open_support=True)["customers"]
    next_products = find_high_cancellation_products(session, limit=10, exclude_open_recovery=True)["products"]
    assert customers[0].id not in {item["id"] for item in next_customers}
    assert products[0].id not in {item["id"] for item in next_products}
    assert len(next_customers) == 2
    assert len(next_products) == 2


def test_failed_email_delivery_can_be_retried_without_duplicate_rows():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    settings.email_mode = "log"
    customer = Customer(external_id="retry-demo", country="UK", segment="at_risk_high_value", churn_risk=0.9, lifetime_value=500)
    session.add(customer)
    session.commit()
    draft = create_campaign_draft(session, "Retry", "at_risk_high_value", "10% discount", customer_ids=[customer.id])
    approval = request_campaign_approval(session, draft["campaign_id"], "Manager gate")
    decide_campaign_approval(session, approval["approval_id"], True, "tester")
    delivery = session.query(EmailDelivery).one()
    delivery.status, delivery.error = "failed", "temporary SMTP failure"
    session.commit()
    result = retry_campaign_delivery(session, draft["campaign_id"])
    assert result["simulated"] == 1
    assert result["failed"] == 0
    assert session.query(EmailDelivery).count() == 1


def test_outcome_requires_real_or_simulated_delivery():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    customer = Customer(external_id="no-email", country="UK", segment="at_risk_high_value", churn_risk=0.9, lifetime_value=500)
    session.add(customer)
    session.commit()
    draft = create_campaign_draft(session, "No delivery", "at_risk_high_value", "10% discount", customer_ids=[customer.id])
    from app.models import Campaign
    campaign = session.get(Campaign, draft["campaign_id"])
    campaign.status = "active"
    session.commit()
    try:
        simulate_campaign_outcome(session, campaign.id)
        assert False, "outcome must require delivery evidence"
    except ValueError as error:
        assert "email is delivered" in str(error)


def test_48_case_agent_evaluation_suite_is_green():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    result = run_offline_evaluations(session)
    assert result["scores"]["cases"] == 48
    assert result["scores"]["intent_accuracy"] == 1.0
    assert result["scores"]["unsafe_action_prevention"] == 1.0
