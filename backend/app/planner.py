"""Constrained autonomous planning and replanning for CustomerPulse."""
import json
from typing import Any

from .config import settings
from .reasoner import AgentRoute


ACTION_DESCRIPTIONS = {
    "knowledge": "Explain the application, metrics, agents, and policies.",
    "top_customers": "Rank customers by total spend.",
    "customer_detail": "Retrieve one customer profile.",
    "purchase_history": "Retrieve one customer's invoices.",
    "country_customers": "Find customers in a country.",
    "risk_customers": "Find high-risk or retention-eligible customers.",
    "product_signals": "Inspect cancellation and declining-product signals.",
    "memory_search": "Retrieve prior operational learnings.",
    "campaign_draft": "Create a customer-specific draft campaign.",
    "campaign_approval": "Submit a draft campaign for manager approval.",
    "support_cases": "Create deduplicated internal support cases.",
    "product_recovery_tasks": "Create deduplicated internal product recovery tasks.",
    "list_tasks": "List open operational tasks.",
    "campaign_outcome": "Complete a campaign outcome simulation and store the learning.",
}

AGENTS = {
    "knowledge": "Knowledge Agent", "top_customers": "Customer Intelligence Agent", "customer_detail": "Customer Intelligence Agent",
    "purchase_history": "Customer Intelligence Agent", "country_customers": "Customer Intelligence Agent", "risk_customers": "Customer Intelligence Agent",
    "product_signals": "Product Intelligence Agent", "memory_search": "Memory Agent", "campaign_draft": "Campaign & Safety Agent",
    "campaign_approval": "Campaign & Safety Agent", "support_cases": "Customer Care Agent", "product_recovery_tasks": "Product Operations Agent",
    "list_tasks": "Operations Agent", "campaign_outcome": "Learning Agent",
}

TEMPLATES = {
    "help": ["knowledge"],
    "top_customers": ["top_customers"],
    "customer_detail": ["customer_detail"],
    "purchase_history": ["purchase_history"],
    "country_customers": ["country_customers"],
    "churn_analysis": ["risk_customers", "product_signals", "memory_search"],
    "retention_campaign": ["risk_customers", "product_signals", "memory_search", "campaign_draft", "campaign_approval"],
    "support_triage": ["risk_customers", "support_cases"],
    "product_recovery": ["product_signals", "product_recovery_tasks"],
    "operational_tasks": ["list_tasks"],
    "campaign_outcome": ["campaign_outcome", "memory_search"],
}

WRITE_ACTIONS = {"campaign_draft", "campaign_approval", "support_cases", "product_recovery_tasks", "campaign_outcome"}


def _allowed(route: AgentRoute) -> set[str]:
    allowed = set(ACTION_DESCRIPTIONS) - WRITE_ACTIONS
    if route.intent == "retention_campaign": allowed |= {"campaign_draft", "campaign_approval"}
    if route.intent == "support_triage": allowed.add("support_cases")
    if route.intent == "product_recovery": allowed.add("product_recovery_tasks")
    if route.intent == "campaign_outcome": allowed.add("campaign_outcome")
    return allowed


def _steps(actions: list[str], rationale: str) -> list[dict[str, str]]:
    return [{"action": action, "agent": AGENTS[action], "objective": ACTION_DESCRIPTIONS[action], "rationale": rationale} for action in actions]


def build_plan(goal: str, route: AgentRoute) -> list[dict[str, str]]:
    fallback = _steps(TEMPLATES[route.intent], route.rationale)
    if not settings.groq_api_key:
        return fallback
    allowed = _allowed(route)
    try:
        from groq import Groq
        response = Groq(api_key=settings.groq_api_key).chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an autonomous customer-operations planner. Choose the smallest evidence-driven plan. Respect the allowed action list exactly. Read-only requests must never gain write actions. Return JSON only."},
                {"role": "user", "content": f"Goal: {goal}\nIntent: {route.intent}\nAllowed actions: {json.dumps({key: ACTION_DESCRIPTIONS[key] for key in sorted(allowed)})}\nReturn {{\"actions\": [action names], \"rationale\": \"why this plan\"}}. Include dependencies in execution order and no duplicates."},
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        actions = [item for item in payload.get("actions", []) if item in allowed]
        required_writes = [item for item in TEMPLATES[route.intent] if item in WRITE_ACTIONS]
        if not actions or any(item not in actions for item in required_writes):
            return fallback
        return _steps(actions[: settings.max_agent_steps], str(payload.get("rationale") or route.rationale))
    except Exception:
        return fallback


def replan(goal: str, route: AgentRoute, completed: list[str], remaining: list[dict], latest: dict[str, Any]) -> dict:
    """Observe a result and decide whether to continue, stop, or revise safely."""
    if latest.get("error"):
        return {"decision": "continue", "rationale": "The failed step was recorded; continue with independent remaining work.", "remaining": remaining}
    if completed and completed[-1] == "risk_customers" and not latest.get("customers"):
        safe_remaining = [step for step in remaining if step["action"] not in {"campaign_draft", "campaign_approval", "support_cases"}]
        return {"decision": "finish" if not safe_remaining else "continue", "rationale": "No qualifying customers were found, so dependent write actions were removed.", "remaining": safe_remaining}
    if completed and completed[-1] == "product_signals" and not latest.get("products"):
        safe_remaining = [step for step in remaining if step["action"] != "product_recovery_tasks"]
        return {"decision": "finish" if not safe_remaining else "continue", "rationale": "No qualifying product signals were found, so no recovery tasks are justified.", "remaining": safe_remaining}
    return {"decision": "continue" if remaining else "finish", "rationale": "The observation supports the next planned step." if remaining else "The goal has enough evidence for a final response.", "remaining": remaining}
