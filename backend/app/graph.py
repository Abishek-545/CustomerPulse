"""Autonomous LangGraph planner -> executor -> observer -> replanner loop."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .checkpointing import build_checkpointer
from .config import settings
from .db import SessionLocal
from .mcp_client import mcp_client
from .models import Investigation
from .planner import build_plan, replan
from .reasoner import AgentRoute, route_goal
from . import domain


class AgentState(TypedDict, total=False):
    investigation_id: int
    goal: str
    intent: str
    params: dict[str, Any]
    plan: list[dict[str, str]]
    remaining: list[dict[str, str]]
    completed: list[str]
    observations: dict[str, Any]
    latest: dict[str, Any]
    findings: list[str]
    decision_log: list[dict[str, str]]
    step_count: int
    result: dict[str, Any]
    status: str
    campaign_id: int
    approval_id: int


def planner_agent(state: AgentState) -> AgentState:
    route = route_goal(state["goal"])
    plan = build_plan(state["goal"], route)
    visible_plan = [f"{step['agent']}: {step['objective']}" for step in plan]
    with SessionLocal() as session:
        item = session.get(Investigation, state["investigation_id"])
        item.plan = visible_plan
        session.commit()
    return {
        "intent": route.intent,
        "params": route.model_dump(),
        "plan": plan,
        "remaining": plan,
        "completed": [],
        "observations": {},
        "findings": [f"Supervisor planned autonomously: {route.rationale}"],
        "decision_log": [{"decision": "plan", "rationale": plan[0]["rationale"] if plan else route.rationale}],
        "step_count": 0,
        "status": "running",
    }


def _execute_action(action: str, state: AgentState) -> tuple[str | None, dict]:
    params, observations = state["params"], state.get("observations", {})
    investigation_id = state["investigation_id"]
    if action == "knowledge":
        tool, output = "knowledge.explain_platform", mcp_client.call_tool("knowledge.explain_platform", question=state["goal"])
    elif action == "top_customers":
        tool, output = "customer.top_customers_by_lifetime_value", mcp_client.call_tool("customer.top_customers_by_lifetime_value", limit=params["limit"])
    elif action == "customer_detail":
        tool, output = "customer.get_customer_by_external_id", mcp_client.call_tool("customer.get_customer_by_external_id", external_id=params["customer_external_id"])
    elif action == "purchase_history":
        tool, output = "customer.get_purchase_history_by_external_id", mcp_client.call_tool("customer.get_purchase_history_by_external_id", external_id=params["customer_external_id"], limit=params["limit"])
    elif action == "country_customers":
        tool, output = "customer.find_customers_by_country", mcp_client.call_tool("customer.find_customers_by_country", country=params["country"], limit=params["limit"])
    elif action == "risk_customers":
        if state["intent"] == "retention_campaign":
            tool, output = "customer.find_eligible_retention_customers", mcp_client.call_tool("customer.find_eligible_retention_customers", limit=params["limit"])
        else:
            tool, output = "customer.find_churn_risk_customers", mcp_client.call_tool("customer.find_churn_risk_customers", min_risk=0.65, limit=params["limit"], exclude_open_support=state["intent"] == "support_triage")
    elif action == "product_signals":
        tool, output = "product.find_high_cancellation_products", mcp_client.call_tool("product.find_high_cancellation_products", threshold=0.10, limit=params["limit"], exclude_open_recovery=state["intent"] == "product_recovery")
    elif action == "memory_search":
        tool, output = "memory.search_memories", mcp_client.call_tool("memory.search_memories", query="campaign outcome offer retention", limit=5)
    elif action == "campaign_draft":
        customers = observations.get("risk_customers", {}).get("customers", [])
        ids = [item["id"] for item in customers if item.get("segment") == "at_risk_high_value"]
        tool = "campaign.create_campaign_draft"
        output = mcp_client.call_tool(tool, name="Win-back: high-value inactive customers", segment="at_risk_high_value", offer="10% welcome-back discount", investigation_id=investigation_id, customer_ids=ids) if ids else {"created": False, "target_count": 0, "reason": "No eligible customers"}
    elif action == "campaign_approval":
        draft = observations.get("campaign_draft", {})
        if not draft.get("campaign_id"):
            return None, {"created": False, "reason": "No draft exists, so approval was skipped"}
        tool = "campaign.request_campaign_approval"
        output = mcp_client.call_tool(tool, campaign_id=draft["campaign_id"], reason=f"Approve discount email for {draft['target_count']} deduplicated customers.")
    elif action == "support_cases":
        customers = observations.get("risk_customers", {}).get("customers", [])
        tool = "operations.create_support_cases_for_customers"
        output = mcp_client.call_tool(tool, customer_ids=[item["id"] for item in customers], title="Proactive high-risk customer review", priority="high", investigation_id=investigation_id)
    elif action == "product_recovery_tasks":
        products = observations.get("product_signals", {}).get("products", [])
        tool = "operations.create_product_recovery_tasks"
        output = mcp_client.call_tool(tool, product_ids=[item["id"] for item in products], investigation_id=investigation_id)
    elif action == "list_tasks":
        tool, output = "operations.list_operational_tasks", mcp_client.call_tool("operations.list_operational_tasks", limit=params["limit"])
    elif action == "campaign_outcome":
        tool, output = "campaign.simulate_campaign_outcome", mcp_client.call_tool("campaign.simulate_campaign_outcome", campaign_id=params["campaign_id"])
    else:
        raise ValueError(f"Unknown autonomous action: {action}")
    return tool, output


def executor_agent(state: AgentState) -> AgentState:
    step = state["remaining"][0]
    action, sequence = step["action"], state.get("step_count", 0) + 1
    tool_name = None
    try:
        tool_name, output = _execute_action(action, state)
        status = "complete"
    except Exception as error:
        output = {"error": f"{type(error).__name__}: {error}"}
        status = "failed"
    with SessionLocal() as session:
        domain.record_agent_step(session, state["investigation_id"], sequence, step["agent"], action, tool_name, step["rationale"], {"goal": state["goal"], "params": state["params"]}, output, status)
    observations = {**state.get("observations", {}), action: output}
    update: AgentState = {
        "latest": output,
        "observations": observations,
        "completed": state.get("completed", []) + [action],
        "remaining": state["remaining"][1:],
        "step_count": sequence,
        "findings": state.get("findings", []) + [f"{step['agent']} observed: {action} {status}."],
    }
    if action == "campaign_draft" and output.get("campaign_id"):
        update["campaign_id"] = output["campaign_id"]
    if action == "campaign_approval" and output.get("approval_id"):
        update["approval_id"] = output["approval_id"]
        update["status"] = "awaiting_approval"
    return update


def observer_agent(state: AgentState) -> AgentState:
    route = AgentRoute.model_validate(state["params"])
    decision = replan(state["goal"], route, state["completed"], state["remaining"], state["latest"])
    remaining = decision["remaining"]
    if state["step_count"] >= settings.max_agent_steps:
        remaining = []
        decision = {"decision": "finish", "rationale": f"Safety step limit of {settings.max_agent_steps} reached.", "remaining": []}
    return {
        "remaining": remaining,
        "decision_log": state.get("decision_log", []) + [{"decision": decision["decision"], "rationale": decision["rationale"]}],
        "findings": state.get("findings", []) + [f"Observer/Replanner: {decision['rationale']}"],
    }


def continue_or_respond(state: AgentState) -> str:
    return "execute" if state.get("remaining") and state.get("step_count", 0) < settings.max_agent_steps else "respond"


def response_agent(state: AgentState) -> AgentState:
    intent, observations = state["intent"], state.get("observations", {})
    direct_data = observations.get({
        "help": "knowledge", "top_customers": "top_customers", "customer_detail": "customer_detail", "purchase_history": "purchase_history",
        "country_customers": "country_customers", "operational_tasks": "list_tasks", "campaign_outcome": "campaign_outcome",
    }.get(intent, "risk_customers"), {})
    agents = list(dict.fromkeys(step["agent"] for step in state.get("plan", []))) + ["Observer/Replanner", "Response Agent"]
    if intent == "retention_campaign":
        draft, approval = observations.get("campaign_draft", {}), observations.get("campaign_approval", {})
        created = bool(draft.get("campaign_id"))
        result = {"kind": "campaign", "created": created, **draft, "approval_id": approval.get("approval_id"), "agents": agents, "decision_log": state.get("decision_log", []), "summary": f"Autonomous plan created a draft for {draft.get('target_count', 0)} unique customers and paused for manager approval." if created else "No eligible customers remained, so the autonomous agent safely created nothing."}
    elif intent in ("support_triage", "product_recovery"):
        action = "support_cases" if intent == "support_triage" else "product_recovery_tasks"
        data = observations.get(action, {})
        created, existing = data.get("created_count", 0), data.get("existing_count", data.get("duplicates_skipped", 0))
        summary = f"Autonomous operations created {created} new record{'s' if created != 1 else ''}."
        if existing:
            summary += f" {existing} matching open record{'s' if existing != 1 else ''} already existed and were not duplicated."
        if not created and not existing:
            summary = "No unhandled qualifying records were found, so the agent safely created nothing."
        result = {"kind": intent, "data": data, "agents": agents, "decision_log": state.get("decision_log", []), "summary": summary}
    else:
        result = {"kind": intent, "data": direct_data, "supporting_evidence": {key: value for key, value in observations.items() if value is not direct_data}, "agents": agents, "decision_log": state.get("decision_log", []), "summary": "Autonomous read-only investigation completed; observations were checked after every tool call." if intent != "campaign_outcome" else "Campaign outcome was completed and its learning was saved to long-term memory."}
    status = state.get("status", "complete")
    if status == "running":
        status = "complete"
    with SessionLocal() as session:
        item = session.get(Investigation, state["investigation_id"])
        item.status = status
        item.findings = state.get("findings", []) + [result["summary"]]
        session.commit()
    return {"status": status, "result": result}


workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_agent)
workflow.add_node("execute", executor_agent)
workflow.add_node("observe", observer_agent)
workflow.add_node("respond", response_agent)
workflow.add_edge(START, "planner")
workflow.add_edge("planner", "execute")
workflow.add_edge("execute", "observe")
workflow.add_conditional_edges("observe", continue_or_respond, {"execute": "execute", "respond": "respond"})
workflow.add_edge("respond", END)
checkpointer, CHECKPOINT_BACKEND = build_checkpointer()
agent_graph = workflow.compile(checkpointer=checkpointer)


def run_investigation(goal: str) -> dict:
    with SessionLocal() as session:
        investigation = Investigation(goal=goal, status="running")
        session.add(investigation)
        session.commit()
        investigation_id = investigation.id
    try:
        state = agent_graph.invoke({"investigation_id": investigation_id, "goal": goal}, {"configurable": {"thread_id": f"investigation-{investigation_id}"}})
        return {"investigation_id": investigation_id, "checkpoint_backend": CHECKPOINT_BACKEND, **state}
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        with SessionLocal() as session:
            investigation = session.get(Investigation, investigation_id)
            investigation.status = "failed"
            investigation.findings = [f"Agent execution failed: {message}"]
            session.commit()
        return {"investigation_id": investigation_id, "status": "failed", "error": message, "checkpoint_backend": CHECKPOINT_BACKEND}
