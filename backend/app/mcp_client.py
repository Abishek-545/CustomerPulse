"""Agent-facing MCP tool gateway.

In local mode it dispatches to the same typed operations served by the MCP servers.
The interface intentionally mirrors an MCP client so a Streamable HTTP client can replace
this adapter without changing the LangGraph workflow.
"""
from .db import SessionLocal
from . import domain


class CustomerPulseMCPClient:
    def call_tool(self, tool_name: str, **arguments) -> dict:
        with SessionLocal() as session:
            tools = {
                "customer.find_churn_risk_customers": domain.find_churn_risk_customers,
                "customer.top_customers_by_lifetime_value": domain.top_customers_by_lifetime_value,
                "customer.find_customers_by_country": domain.find_customers_by_country,
                "customer.get_customer_purchase_history": domain.get_customer_purchase_history,
                "customer.get_customer_profile": domain.get_customer_profile,
                "customer.assign_customer_segment": domain.assign_customer_segment,
                "product.get_product_performance": domain.get_product_performance,
                "product.find_high_cancellation_products": domain.find_high_cancellation_products,
                "campaign.create_campaign_draft": domain.create_campaign_draft,
                "campaign.request_campaign_approval": domain.request_campaign_approval,
                "memory.search_memories": domain.search_memories,
                "memory.save_business_learning": domain.save_business_learning,
            }
            if tool_name not in tools:
                raise ValueError(f"Tool is not allowlisted: {tool_name}")
            return tools[tool_name](session, **arguments)


mcp_client = CustomerPulseMCPClient()
