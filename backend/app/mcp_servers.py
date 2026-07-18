"""Runnable MCP domain servers. Run one with: python -m app.mcp_servers customer"""
import sys
from mcp.server.fastmcp import FastMCP
from .db import SessionLocal
from . import domain


def customer_server() -> FastMCP:
    mcp = FastMCP("customerpulse-customer")

    @mcp.resource("customer://segments")
    def segment_definitions() -> str:
        return "at_risk_high_value: total spend >= £250 and churn risk >= 65%; active: every imported customer who does not meet that combined rule; seeded demo data may also use champion, new, or unsegmented"

    @mcp.prompt()
    def investigate_churn(segment: str = "at_risk_high_value") -> str:
        return f"Investigate the {segment} customer segment. Use customer tools, cite observations, and do not contact customers."

    @mcp.tool()
    def find_churn_risk_customers(min_risk: float = 0.65, limit: int = 20) -> dict:
        with SessionLocal() as session:
            return domain.find_churn_risk_customers(session, min_risk, limit)

    @mcp.tool()
    def find_eligible_retention_customers(limit: int = 20) -> dict:
        with SessionLocal() as session:
            return domain.find_eligible_retention_customers(session, limit)

    @mcp.tool()
    def top_customers_by_lifetime_value(limit: int = 5) -> dict:
        with SessionLocal() as session:
            return domain.top_customers_by_lifetime_value(session, limit)

    @mcp.tool()
    def find_customers_by_country(country: str, limit: int = 20) -> dict:
        with SessionLocal() as session:
            return domain.find_customers_by_country(session, country, limit)

    @mcp.tool()
    def get_customer_purchase_history(customer_id: int, limit: int = 20) -> dict:
        with SessionLocal() as session:
            return domain.get_customer_purchase_history(session, customer_id, limit)

    @mcp.tool()
    def get_customer_profile(customer_id: int) -> dict:
        with SessionLocal() as session:
            return domain.get_customer_profile(session, customer_id)

    @mcp.tool()
    def get_customer_by_external_id(external_id: str) -> dict:
        with SessionLocal() as session:
            return domain.get_customer_by_external_id(session, external_id)

    @mcp.tool()
    def get_purchase_history_by_external_id(external_id: str, limit: int = 20) -> dict:
        with SessionLocal() as session:
            return domain.get_purchase_history_by_external_id(session, external_id, limit)

    @mcp.tool()
    def assign_customer_segment(customer_id: int, segment: str) -> dict:
        with SessionLocal() as session:
            return domain.assign_customer_segment(session, customer_id, segment)
    return mcp


def product_server() -> FastMCP:
    mcp = FastMCP("customerpulse-product")

    @mcp.resource("product://metric-definitions")
    def metric_definitions() -> str:
        return "cancellation_rate is cancelled orders / total orders; sales_trend is recent period growth, where negative values indicate decline."

    @mcp.prompt()
    def investigate_product_decline() -> str:
        return "Investigate declining products with deterministic metrics before suggesting a customer action."

    @mcp.tool()
    def get_product_performance(limit: int = 10) -> dict:
        with SessionLocal() as session:
            return domain.get_product_performance(session, limit)

    @mcp.tool()
    def find_high_cancellation_products(threshold: float = 0.10, limit: int = 10) -> dict:
        with SessionLocal() as session:
            return domain.find_high_cancellation_products(session, threshold, limit)
    return mcp


def campaign_server() -> FastMCP:
    mcp = FastMCP("customerpulse-campaign")

    @mcp.resource("campaign://approval-policy")
    def approval_policy() -> str:
        return "All campaigns begin as drafts. Only an approved campaign may become active and trigger email delivery. Demo recipients are overridden to one configured safety inbox."

    @mcp.prompt()
    def create_retention_campaign() -> str:
        return "Create a narrowly targeted draft after evidence is collected. Always submit it for human approval."

    @mcp.tool()
    def create_campaign_draft(name: str, segment: str, offer: str, customer_ids: list[int], investigation_id: int | None = None) -> dict:
        with SessionLocal() as session:
            return domain.create_campaign_draft(session, name, segment, offer, investigation_id, customer_ids)

    @mcp.tool()
    def request_campaign_approval(campaign_id: int, reason: str) -> dict:
        with SessionLocal() as session:
            return domain.request_campaign_approval(session, campaign_id, reason)

    @mcp.tool()
    def campaign_delivery_status(campaign_id: int) -> dict:
        with SessionLocal() as session:
            return domain.campaign_delivery_status(session, campaign_id)

    @mcp.tool()
    def simulate_campaign_outcome(campaign_id: int) -> dict:
        with SessionLocal() as session:
            return domain.simulate_campaign_outcome(session, campaign_id)
    return mcp


def memory_server() -> FastMCP:
    mcp = FastMCP("customerpulse-memory")

    @mcp.resource("memory://business-rules")
    def business_rules() -> str:
        return "Use prior outcomes as supporting evidence, not as proof. Never activate a campaign without an approval record."

    @mcp.tool()
    def search_memories(query: str, limit: int = 5) -> dict:
        with SessionLocal() as session:
            return domain.search_memories(session, query, limit)

    @mcp.tool()
    def save_business_learning(category: str, content: str, confidence: float = 0.75) -> dict:
        with SessionLocal() as session:
            return domain.save_business_learning(session, category, content, confidence)
    return mcp


def knowledge_server() -> FastMCP:
    mcp = FastMCP("customerpulse-knowledge")

    @mcp.resource("knowledge://platform-guide")
    def platform_guide() -> str:
        return "CustomerPulse explains retail customer value, inactivity risk, customer groups, specialist-agent roles, campaign safety, and the source of derived metrics."

    @mcp.prompt()
    def explain_customerpulse(question: str = "What does this app do?") -> str:
        return f"Answer this onboarding question in plain English using the platform guide: {question}"

    @mcp.tool()
    def explain_platform(question: str = "What does this app do?") -> dict:
        with SessionLocal() as session:
            return domain.explain_platform(session, question)
    return mcp


def operations_server() -> FastMCP:
    mcp = FastMCP("customerpulse-operations")

    @mcp.resource("operations://action-policy")
    def action_policy() -> str:
        return "Support cases and product recovery tasks are internal reversible records. Customer communications require a manager-approved campaign."

    @mcp.prompt()
    def plan_customer_operations(goal: str) -> str:
        return f"Plan the smallest safe set of internal operational actions for: {goal}. Observe every result and replan when evidence is insufficient."

    @mcp.tool()
    def create_support_cases_for_customers(customer_ids: list[int], title: str, priority: str = "high", investigation_id: int | None = None) -> dict:
        with SessionLocal() as session:
            return domain.create_support_cases_for_customers(session, customer_ids, title, priority, investigation_id)

    @mcp.tool()
    def create_product_recovery_tasks(product_ids: list[int], investigation_id: int | None = None) -> dict:
        with SessionLocal() as session:
            return domain.create_product_recovery_tasks(session, product_ids, investigation_id)

    @mcp.tool()
    def list_operational_tasks(limit: int = 50) -> dict:
        with SessionLocal() as session:
            return domain.list_operational_tasks(session, limit)
    return mcp


SERVERS = {"customer": customer_server, "product": product_server, "campaign": campaign_server, "memory": memory_server, "knowledge": knowledge_server, "operations": operations_server}
if __name__ == "__main__":
    selected = sys.argv[1] if len(sys.argv) > 1 else "customer"
    transport = sys.argv[2] if len(sys.argv) > 2 else "stdio"
    SERVERS[selected]().run(transport=transport)
