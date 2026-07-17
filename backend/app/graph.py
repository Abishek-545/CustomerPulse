from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from .db import SessionLocal
from . import domain
from .mcp_client import mcp_client
from .models import Investigation
from .reasoner import create_plan


class AgentState(TypedDict, total=False):
    investigation_id: int
    goal: str
    plan: list[str]
    observations: list[dict]
    findings: list[str]
    campaign_id: int
    approval_id: int
    status: str
    create_retention_campaign: bool


def plan(state: AgentState) -> AgentState:
    agent_plan = create_plan(state["goal"])
    steps = agent_plan.steps
    with SessionLocal() as session:
        investigation = session.get(Investigation, state["investigation_id"])
        investigation.plan = steps
        session.commit()
    return {"plan": steps, "observations": [], "findings": [f"Planner rationale: {agent_plan.rationale}"], "create_retention_campaign": agent_plan.create_retention_campaign}


def investigate(state: AgentState) -> AgentState:
    with SessionLocal() as session:
        # Calls are intentionally routed through the MCP tool gateway. The gateway
        # enforces the tool allowlist and is replaceable with Streamable HTTP clients.
        churn = mcp_client.call_tool("customer.find_churn_risk_customers", min_risk=0.65, limit=10)
        products = mcp_client.call_tool("product.find_high_cancellation_products", threshold=0.10, limit=10)
        memories = mcp_client.call_tool("memory.search_memories", query="offer", limit=5)
    findings = list(state.get("findings", []))
    if churn["customers"]:
        findings.append(f"Found {len(churn['customers'])} high-risk customers; highest-value customer risk requires retention action.")
    if products["products"]:
        findings.append(f"Found {len(products['products'])} products with elevated cancellation rates.")
    if memories["memories"]:
        findings.append("Found prior business memory relevant to a retention offer.")
    return {"observations": [churn, products, memories], "findings": findings}


def propose(state: AgentState) -> AgentState:
    if not state.get("create_retention_campaign"):
        return {"status": "complete"}
    with SessionLocal() as session:
        draft = mcp_client.call_tool(
            "campaign.create_campaign_draft",
            name="Win-back: high-value inactive customers",
            segment="at_risk_high_value",
            offer="10% welcome-back discount",
            investigation_id=state["investigation_id"],
        )
        approval = mcp_client.call_tool("campaign.request_campaign_approval", campaign_id=draft["campaign_id"], reason="High-value customer retention action requires manager approval.")
        investigation = session.get(Investigation, state["investigation_id"])
        investigation.findings = state["findings"] + ["Created a draft campaign and sent it for human approval."]
        investigation.status = "awaiting_approval"
        session.commit()
    return {"campaign_id": draft["campaign_id"], "approval_id": approval["approval_id"], "status": "awaiting_approval"}


def learn(state: AgentState) -> AgentState:
    if state.get("status") == "awaiting_approval":
        return state
    with SessionLocal() as session:
        domain.save_business_learning(session, "investigation", f"Completed investigation: {state['goal']}. Findings: {' '.join(state.get('findings', []))}")
        investigation = session.get(Investigation, state["investigation_id"])
        investigation.status = "complete"
        investigation.findings = state.get("findings", [])
        session.commit()
    return {"status": "complete"}


workflow = StateGraph(AgentState)
workflow.add_node("plan", plan)
workflow.add_node("investigate", investigate)
workflow.add_node("propose", propose)
workflow.add_node("learn", learn)
workflow.add_edge(START, "plan")
workflow.add_edge("plan", "investigate")
workflow.add_edge("investigate", "propose")
workflow.add_edge("propose", "learn")
workflow.add_edge("learn", END)
agent_graph = workflow.compile(checkpointer=MemorySaver())


def run_investigation(goal: str) -> dict:
    with SessionLocal() as session:
        investigation = Investigation(goal=goal, status="running")
        session.add(investigation)
        session.commit()
        investigation_id = investigation.id
    state = agent_graph.invoke({"investigation_id": investigation_id, "goal": goal}, {"configurable": {"thread_id": f"investigation-{investigation_id}"}})
    return {"investigation_id": investigation_id, **state}
