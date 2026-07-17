"""Runnable MCP domain servers. Run one with: python -m app.mcp_servers customer"""
import sys
from mcp.server.fastmcp import FastMCP
from .db import SessionLocal
from . import domain


def customer_server() -> FastMCP:
    mcp = FastMCP("customerpulse-customer")

    @mcp.resource("customer://segments")
    def segment_definitions() -> str:
        return "champion: frequent/high value; at_risk_high_value: valuable but inactive; new: recently acquired; unsegmented: not yet classified"

    @mcp.prompt()
    def investigate_churn(segment: str = "at_risk_high_value") -> str:
        return f"Investigate the {segment} customer segment. Use customer tools, cite observations, and do not contact customers."

    @mcp.tool()
    def find_churn_risk_customers(min_risk: float = 0.65, limit: int = 20) -> dict:
        with SessionLocal() as session:
            return domain.find_churn_risk_customers(session, min_risk, limit)

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
        return "All campaigns begin as drafts. Only an approved campaign may become active. No external communications are sent by this demo."

    @mcp.prompt()
    def create_retention_campaign() -> str:
        return "Create a narrowly targeted draft after evidence is collected. Always submit it for human approval."

    @mcp.tool()
    def create_campaign_draft(name: str, segment: str, offer: str) -> dict:
        with SessionLocal() as session:
            return domain.create_campaign_draft(session, name, segment, offer)

    @mcp.tool()
    def request_campaign_approval(campaign_id: int, reason: str) -> dict:
        with SessionLocal() as session:
            return domain.request_campaign_approval(session, campaign_id, reason)
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


SERVERS = {"customer": customer_server, "product": product_server, "campaign": campaign_server, "memory": memory_server}
if __name__ == "__main__":
    selected = sys.argv[1] if len(sys.argv) > 1 else "customer"
    SERVERS[selected]().run()
