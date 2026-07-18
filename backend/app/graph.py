"""Intent-aware multi-agent workflow.

The supervisor delegates to specialist agents. They communicate through the
typed LangGraph state, and only the campaign agent is allowed to create data.
"""
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .db import SessionLocal
from .mcp_client import mcp_client
from .models import Investigation
from .reasoner import route_goal


class AgentState(TypedDict, total=False):
    investigation_id: int
    goal: str
    intent: str
    params: dict[str, Any]
    plan: list[str]
    observations: dict[str, Any]
    findings: list[str]
    result: dict[str, Any]
    status: str
    campaign_id: int
    approval_id: int


def supervisor_agent(state: AgentState) -> AgentState:
    route = route_goal(state["goal"])
    plans = {
        "help": ["Supervisor identifies an onboarding question", "Knowledge Agent reads the MCP platform guide", "Response Agent explains the product in plain English"],
        "top_customers": ["Supervisor routes read-only request", "Customer Intelligence Agent ranks lifetime value", "Response Agent formats evidence"],
        "customer_detail": ["Supervisor extracts customer ID", "Customer Intelligence Agent retrieves profile", "Response Agent explains metrics"],
        "purchase_history": ["Supervisor extracts customer ID", "Customer Intelligence Agent retrieves orders", "Response Agent formats purchase history"],
        "country_customers": ["Supervisor extracts location", "Customer Intelligence Agent filters geography", "Response Agent ranks matching customers"],
        "churn_analysis": ["Customer Intelligence Agent identifies risk", "Product Agent inspects product signals", "Memory Agent retrieves prior learnings", "Response Agent synthesizes findings"],
        "retention_campaign": ["Customer Intelligence Agent selects eligible customers", "Product Agent validates signals", "Memory Agent retrieves policy context", "Campaign Agent excludes duplicate targets", "Safety gate requests human approval"],
    }
    plan = plans[route.intent]
    with SessionLocal() as session:
        item = session.get(Investigation, state["investigation_id"])
        item.plan = plan
        session.commit()
    return {"intent": route.intent, "params": route.model_dump(), "plan": plan, "observations": {}, "findings": [f"Supervisor: {route.rationale}"]}


def knowledge_agent(state: AgentState) -> AgentState:
    if state["intent"] != "help":
        return {}
    data = mcp_client.call_tool("knowledge.explain_platform", question=state["goal"])
    return {"observations": {**state.get("observations", {}), "knowledge_agent": data}, "findings": state["findings"] + ["Knowledge Agent retrieved the MCP platform guide and business glossary."]}


def customer_intelligence_agent(state: AgentState) -> AgentState:
    intent, params = state["intent"], state["params"]
    if intent == "help":
        return {}
    if intent == "top_customers":
        data = mcp_client.call_tool("customer.top_customers_by_lifetime_value", limit=params["limit"])
    elif intent == "customer_detail":
        data = mcp_client.call_tool("customer.get_customer_by_external_id", external_id=params["customer_external_id"])
    elif intent == "purchase_history":
        data = mcp_client.call_tool("customer.get_purchase_history_by_external_id", external_id=params["customer_external_id"], limit=params["limit"])
    elif intent == "country_customers":
        data = mcp_client.call_tool("customer.find_customers_by_country", country=params["country"], limit=params["limit"])
    elif intent == "retention_campaign":
        data = mcp_client.call_tool("customer.find_eligible_retention_customers", limit=params["limit"])
    else:
        data = mcp_client.call_tool("customer.find_churn_risk_customers", min_risk=0.65, limit=params["limit"])
    observations = {**state.get("observations", {}), "customer_agent": data}
    return {"observations": observations, "findings": state["findings"] + ["Customer Intelligence Agent completed its MCP data query."]}


def product_intelligence_agent(state: AgentState) -> AgentState:
    if state["intent"] not in ("churn_analysis", "retention_campaign"):
        return {}
    data = mcp_client.call_tool("product.find_high_cancellation_products", threshold=0.10, limit=10)
    return {"observations": {**state["observations"], "product_agent": data}, "findings": state["findings"] + ["Product Intelligence Agent checked cancellation signals."]}


def memory_agent(state: AgentState) -> AgentState:
    if state["intent"] not in ("churn_analysis", "retention_campaign"):
        return {}
    data = mcp_client.call_tool("memory.search_memories", query="offer", limit=5)
    return {"observations": {**state["observations"], "memory_agent": data}, "findings": state["findings"] + ["Memory Agent retrieved relevant business learnings."]}


def campaign_agent(state: AgentState) -> AgentState:
    if state["intent"] != "retention_campaign":
        return {}
    customers = state["observations"]["customer_agent"].get("customers", [])
    target_ids = [item["id"] for item in customers if item.get("segment") == "at_risk_high_value"]
    if not target_ids:
        return {"status": "complete", "result": {"kind": "campaign", "created": False, "summary": "No eligible high-value customers remain; no duplicate campaign was created.", "target_count": 0}}
    try:
        draft = mcp_client.call_tool(
            "campaign.create_campaign_draft",
            name="Win-back: high-value inactive customers",
            segment="at_risk_high_value",
            offer="10% welcome-back discount",
            investigation_id=state["investigation_id"],
            customer_ids=target_ids,
        )
    except ValueError:
        return {"status": "complete", "result": {"kind": "campaign", "created": False, "summary": "Eligible customers were claimed by another campaign; no duplicate was created.", "target_count": 0}}
    approval = mcp_client.call_tool("campaign.request_campaign_approval", campaign_id=draft["campaign_id"], reason=f"Approve retention action for {draft['target_count']} specifically identified customers.")
    return {
        "campaign_id": draft["campaign_id"], "approval_id": approval["approval_id"], "status": "awaiting_approval",
        "result": {"kind": "campaign", "created": True, **draft, "summary": f"Draft campaign targets {draft['target_count']} customers and excluded {draft['excluded_existing_targets']} duplicates."},
        "findings": state["findings"] + [f"Campaign Agent selected {draft['target_count']} unique customers and requested approval."],
    }


def response_agent(state: AgentState) -> AgentState:
    default_data = state["observations"].get("knowledge_agent", {}) if state["intent"] == "help" else state["observations"].get("customer_agent", {})
    default_agents = ["Supervisor", "Knowledge"] if state["intent"] == "help" else ["Supervisor", "Customer Intelligence"] + (["Product Intelligence", "Memory"] if state["intent"] == "churn_analysis" else [])
    result = state.get("result") or {
        "kind": state["intent"],
        "data": default_data,
        "supporting_evidence": {key: value for key, value in state["observations"].items() if key not in ("customer_agent", "knowledge_agent")},
        "agents": default_agents + ["Response"],
        "summary": "Platform guidance completed. No data was changed." if state["intent"] == "help" else "Read-only request completed. No campaign was created.",
    }
    status = state.get("status", "complete")
    with SessionLocal() as session:
        item = session.get(Investigation, state["investigation_id"])
        item.status = status
        item.findings = state.get("findings", []) + [result["summary"]]
        session.commit()
    return {"status": status, "result": result}


workflow = StateGraph(AgentState)
workflow.add_node("supervisor", supervisor_agent)
workflow.add_node("knowledge", knowledge_agent)
workflow.add_node("customer_intelligence", customer_intelligence_agent)
workflow.add_node("product_intelligence", product_intelligence_agent)
workflow.add_node("memory", memory_agent)
workflow.add_node("campaign", campaign_agent)
workflow.add_node("response", response_agent)
workflow.add_edge(START, "supervisor")
workflow.add_edge("supervisor", "knowledge")
workflow.add_edge("knowledge", "customer_intelligence")
workflow.add_edge("customer_intelligence", "product_intelligence")
workflow.add_edge("product_intelligence", "memory")
workflow.add_edge("memory", "campaign")
workflow.add_edge("campaign", "response")
workflow.add_edge("response", END)
agent_graph = workflow.compile(checkpointer=MemorySaver())


def run_investigation(goal: str) -> dict:
    with SessionLocal() as session:
        investigation = Investigation(goal=goal, status="running")
        session.add(investigation)
        session.commit()
        investigation_id = investigation.id
    try:
        state = agent_graph.invoke({"investigation_id": investigation_id, "goal": goal}, {"configurable": {"thread_id": f"investigation-{investigation_id}"}})
        return {"investigation_id": investigation_id, **state}
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        with SessionLocal() as session:
            investigation = session.get(Investigation, investigation_id)
            investigation.status = "failed"
            investigation.findings = [f"Agent execution failed: {message}"]
            session.commit()
        return {"investigation_id": investigation_id, "status": "failed", "error": message}
