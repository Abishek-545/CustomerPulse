"""Groq-powered planning with a deterministic fallback for local demos and tests."""
import json
from pydantic import BaseModel, Field
from .config import settings


class InvestigationPlan(BaseModel):
    steps: list[str] = Field(min_length=3, max_length=7)
    create_retention_campaign: bool
    rationale: str


def create_plan(goal: str) -> InvestigationPlan:
    fallback = InvestigationPlan(
        steps=["Inspect customer risk and value", "Inspect product cancellation and sales signals", "Retrieve relevant business memories", "Create a retention campaign draft", "Request human approval"],
        create_retention_campaign=any(word in goal.lower() for word in ("churn", "retain", "customer", "campaign")),
        rationale="The goal concerns customer retention, so evidence should be collected before creating a draft action.",
    )
    if not settings.groq_api_key:
        return fallback
    try:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a careful customer operations planner. Return only valid JSON matching the requested schema.",
                },
                {
                    "role": "user",
                    "content": (
                        "Create a short plan for this goal: " + goal + ". You may investigate only customer risk, product performance, "
                        "and business memory. You may only propose a draft campaign; a human must approve activation. "
                        "Return JSON: {\"steps\": [string], \"create_retention_campaign\": boolean, \"rationale\": string}."
                    ),
                },
            ],
        )
        content = response.choices[0].message.content
        return InvestigationPlan.model_validate(json.loads(content or "{}"))
    except Exception:
        return fallback
