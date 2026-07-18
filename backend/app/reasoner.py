"""Groq-backed intent routing with safe deterministic guards.

Read-only questions can never become campaign actions. Groq is used only after
the explicit business-action phrases are checked.
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from .config import settings


Intent = Literal["help", "top_customers", "customer_detail", "purchase_history", "country_customers", "churn_analysis", "retention_campaign"]


class AgentRoute(BaseModel):
    intent: Intent
    limit: int = Field(default=5, ge=1, le=50)
    customer_external_id: str | None = None
    country: str | None = None
    rationale: str


def _number(text: str, default: int = 5) -> int:
    match = re.search(r"\b(?:top|show|find|list)?\s*(\d{1,2})\b", text)
    return min(50, max(1, int(match.group(1)))) if match else default


def route_goal(goal: str) -> AgentRoute:
    text = goal.strip().lower()
    customer_match = re.search(r"(?:customer|id)\s*#?\s*(\d{3,})", text)
    external_id = customer_match.group(1) if customer_match else None
    if any(phrase in text for phrase in ("create campaign", "draft campaign", "retention campaign", "win-back campaign", "create retention")):
        return AgentRoute(intent="retention_campaign", limit=_number(text, 10), rationale="The user explicitly requested a campaign action, so approval is required.")
    if any(phrase in text for phrase in ("purchase history", "order history", "purchases of", "orders of")):
        return AgentRoute(intent="purchase_history", customer_external_id=external_id, limit=_number(text, 20), rationale="The request asks for historical purchases and is read-only.")
    if external_id and any(word in text for word in ("detail", "profile", "show", "find")):
        return AgentRoute(intent="customer_detail", customer_external_id=external_id, rationale="The request asks for one customer profile and is read-only.")
    if any(phrase in text for phrase in ("what does this app", "what this app", "what is this app", "how does this app", "what is customerpulse", "meaning of", "what does churn", "what is churn", "lifetime value mean", "what is lifetime value", "explain lifetime value", "segment mean", "what is segment", "explain segment", "what are these parameters", "meaning of parameter", "role of multi", "why multi", "what are the agents", "explain the app", "explain this app")):
        return AgentRoute(intent="help", rationale="The request asks for product or metric guidance and is read-only.")
    country_match = re.search(r"(?:customers?\s+in|from|country)\s+([a-z][a-z ]{1,30})", text)
    if country_match:
        country = country_match.group(1).strip().rstrip("?.")
        return AgentRoute(intent="country_customers", country=country.title(), limit=_number(text, 20), rationale="The request filters customers by geography and is read-only.")
    if any(word in text for word in ("churn", "risk", "retain", "retention")):
        return AgentRoute(intent="churn_analysis", limit=_number(text, 10), rationale="The request asks for analysis; no campaign action was explicitly requested.")
    if re.search(r"\btop\s+\d*\s*customers?\b", text) or any(phrase in text for phrase in ("top customer", "top customers", "highest value", "highest lifetime", "top lifetime")):
        return AgentRoute(intent="top_customers", limit=_number(text), rationale="The request asks for a customer ranking and is read-only.")
    return _groq_route(goal)


def _groq_route(goal: str) -> AgentRoute:
    fallback = AgentRoute(intent="help", limit=5, rationale="Ambiguous request handled as safe product guidance.")
    if not settings.groq_api_key:
        return fallback
    try:
        from groq import Groq
        response = Groq(api_key=settings.groq_api_key).chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Route customer-operations requests. Never choose retention_campaign unless the user explicitly asks to create or draft a campaign. Return JSON only."},
                {"role": "user", "content": f"Request: {goal}\nReturn intent (help, top_customers, customer_detail, purchase_history, country_customers, churn_analysis, retention_campaign), limit, customer_external_id, country, rationale. Use help for questions about the app, metrics, terminology, or agent roles."},
            ],
        )
        return AgentRoute.model_validate(json.loads(response.choices[0].message.content or "{}"))
    except Exception:
        return fallback
