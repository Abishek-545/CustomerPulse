"""MCP gateway used by LangGraph agents.

Production uses the official Streamable HTTP client with MCP initialization,
capability discovery, and tools/call. Tests and offline development can use the
same allowlisted domain operations directly.
"""
import asyncio
import json
import os
import time
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from . import domain
from .config import settings
from .db import SessionLocal


DIRECT_TOOLS = {
    "customer.find_churn_risk_customers": domain.find_churn_risk_customers,
    "customer.find_eligible_retention_customers": domain.find_eligible_retention_customers,
    "customer.top_customers_by_lifetime_value": domain.top_customers_by_lifetime_value,
    "customer.find_customers_by_country": domain.find_customers_by_country,
    "customer.find_customers_by_minimum_value": domain.find_customers_by_minimum_value,
    "customer.find_frequent_cancellers": domain.find_frequent_cancellers,
    "customer.get_customer_purchase_history": domain.get_customer_purchase_history,
    "customer.get_customer_profile": domain.get_customer_profile,
    "customer.get_customer_by_external_id": domain.get_customer_by_external_id,
    "customer.get_purchase_history_by_external_id": domain.get_purchase_history_by_external_id,
    "customer.assign_customer_segment": domain.assign_customer_segment,
    "product.get_product_performance": domain.get_product_performance,
    "product.find_high_cancellation_products": domain.find_high_cancellation_products,
    "product.analyze_product_portfolio": domain.analyze_product_portfolio,
    "campaign.create_campaign_draft": domain.create_campaign_draft,
    "campaign.request_campaign_approval": domain.request_campaign_approval,
    "campaign.campaign_delivery_status": domain.campaign_delivery_status,
    "campaign.simulate_campaign_outcome": domain.simulate_campaign_outcome,
    "memory.search_memories": domain.search_memories,
    "memory.save_business_learning": domain.save_business_learning,
    "knowledge.explain_platform": domain.explain_platform,
    "operations.create_support_cases_for_customers": domain.create_support_cases_for_customers,
    "operations.create_product_recovery_tasks": domain.create_product_recovery_tasks,
    "operations.list_operational_tasks": domain.list_operational_tasks,
    "operations.update_operational_task_status": domain.update_operational_task_status,
}


class CustomerPulseMCPClient:
    def __init__(self) -> None:
        base = settings.mcp_base_url or os.getenv("RENDER_EXTERNAL_URL")
        self.base_url = base.rstrip("/") if base else None
        self.transport = settings.mcp_transport.lower()
        self._capability_cache: tuple[float, dict] | None = None

    def _uses_http(self) -> bool:
        return self.transport == "streamable-http" or (self.transport == "auto" and bool(self.base_url))

    def _endpoint(self, server: str) -> str:
        if not self.base_url:
            raise RuntimeError("MCP_BASE_URL is required for Streamable HTTP")
        base = self.base_url if self.base_url.endswith("/mcp") else f"{self.base_url}/mcp"
        return f"{base}/{server}/mcp"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.mcp_internal_token}"} if settings.mcp_internal_token else {}

    async def _call_http(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        server, local_name = tool_name.split(".", 1)
        async with streamablehttp_client(self._endpoint(server), headers=self._headers(), timeout=30) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available = {tool.name for tool in (await session.list_tools()).tools}
                if local_name not in available:
                    raise ValueError(f"MCP server {server} does not expose {local_name}")
                result = await session.call_tool(local_name, arguments=arguments)
                if result.isError:
                    message = " ".join(getattr(item, "text", "") for item in result.content)
                    raise RuntimeError(message or f"MCP tool {tool_name} failed")
                structured = getattr(result, "structuredContent", None)
                if structured:
                    return structured
                for item in result.content:
                    text = getattr(item, "text", None)
                    if text:
                        parsed = json.loads(text)
                        return parsed if isinstance(parsed, dict) else {"result": parsed}
                return {"content": [item.model_dump() for item in result.content]}

    async def _discover_http(self) -> dict:
        discovered: dict[str, dict] = {}
        for server in ("customer", "product", "campaign", "memory", "knowledge", "operations"):
            async with streamablehttp_client(self._endpoint(server), headers=self._headers(), timeout=30) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    resources = await session.list_resources()
                    prompts = await session.list_prompts()
                    discovered[server] = {
                        "transport": "streamable-http",
                        "endpoint": self._endpoint(server),
                        "tools": [item.name for item in tools.tools],
                        "resources": [str(item.uri) for item in resources.resources],
                        "prompts": [item.name for item in prompts.prompts],
                    }
        return discovered

    def call_tool(self, tool_name: str, **arguments) -> dict:
        if tool_name not in DIRECT_TOOLS:
            raise ValueError(f"Tool is not allowlisted: {tool_name}")
        if self._uses_http():
            return asyncio.run(self._call_http(tool_name, arguments))
        with SessionLocal() as session:
            return DIRECT_TOOLS[tool_name](session, **arguments)

    def discover(self) -> dict:
        if self._capability_cache and time.monotonic() - self._capability_cache[0] < 300:
            return self._capability_cache[1]
        if self._uses_http():
            result = asyncio.run(self._discover_http())
            self._capability_cache = (time.monotonic(), result)
            return result
        result: dict[str, dict] = {}
        for server in ("customer", "product", "campaign", "memory", "knowledge", "operations"):
            result[server] = {
                "transport": "direct-test-fallback",
                "tools": sorted(name.split(".", 1)[1] for name in DIRECT_TOOLS if name.startswith(f"{server}.")),
                "resources": [],
                "prompts": [],
            }
        self._capability_cache = (time.monotonic(), result)
        return result


mcp_client = CustomerPulseMCPClient()
