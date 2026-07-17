"""LLM planning with a deterministic fallback for local demos and tests."""
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
    if not settings.openai_api_key:
        return fallback
    try:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model=settings.openai_model, temperature=0).with_structured_output(InvestigationPlan)
        return model.invoke(
            "You are a customer operations planner. Create a short investigation plan for this goal: "
            f"{goal}. You may only investigate customer risk, product performance, and business memory. "
            "You may only propose a draft campaign; a human must approve activation."
        )
    except Exception:
        return fallback
