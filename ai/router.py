"""
AI intent router.

Classifies every user request into exactly one of the supported
intents so the orchestration layer can dispatch it to the correct
handler.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from logging import Logger
from typing import Any, Dict, List

from models.common import BaseSchema
from utils.exceptions import LlmError, ServiceError

from .llm import GroqLLM


class IntentType(str, Enum):
    """
    The ten operations the AI assistant can perform.
    """

    CRUD = "CRUD"
    """Create, read, update, delete employees."""

    ANALYTICS = "Analytics"
    """Aggregate queries — counts, averages, reports, charts."""

    SEMANTIC_SEARCH = "SemanticSearch"
    """Natural-language similarity search over employee data."""

    SQL = "SQL"
    """Read-only SQL question answering."""

    HISTORY = "History"
    """Career timeline and stall-detection queries for employees."""

    RECOMMENDATION = "Recommendation"
    """Rank candidates for a role with requirements and location."""

    TEAMBUILD = "TeamBuild"
    """Assemble a multi-role team from a project brief."""

    PROMOTION = "Promotion"
    """Identify employees ready for promotion."""

    TRANSFER = "Transfer"
    """Suggest internal department transfers."""

    ATTRITION = "Attrition"
    """Identify attrition risk factors."""

    SKILLGAP = "SkillGap"
    """Identify skill gaps and estimate hiring cost."""

    INSIGHTS = "Insights"
    """History-backed workforce scorecard."""

    PLANNER = "Planner"
    """Multi-step / executive questions that need agent orchestration."""


class RouterDecision(BaseSchema):
    """
    Structured result of intent classification.
    """

    intent: IntentType
    """The classified intent."""

    reasoning: str
    """Short explanation of why this intent was chosen."""

    confidence: float
    """Confidence score between 0 and 1."""


ROUTER_SYSTEM_PROMPT = """\
You are an HR AI assistant router. Your only job is to classify the user's \
request into exactly one of these intents:

- CRUD: Creating, updating, activating, deactivating, or looking up \
employee records by name or ID. Example: "Add a new employee", \
"Show me John's details", "Deactivate EMP005". \
Also use CRUD for "show all employees", "list everyone", \
"show me all employees" — simple list/view requests with no \
filtering or aggregation.

- Analytics: Statistical or aggregate questions about the workforce. \
Example: "How many employees per department?", "Average tenure", \
"Headcount trend over time".

- SemanticSearch: Finding employees by natural-language descriptions, \
skills, or soft criteria. Example: "Find someone with Python experience", \
"Who worked on the payroll project?".

- SQL: Questions that require a database query to answer — typically \
filtered, cross-referenced, or computed queries that aren't simple \
list-all or single-employee lookups. \
Example: "Who joined last month?", "Employees with salary > 100k", \
"Employee count grouped by department and city". \
Do NOT use SQL for "show all employees" or "list everyone" —
those are CRUD.

- History: Questions about a specific employee's career timeline, \
promotion history, role tenure, or stall detection. Example: \
"Show me Rahul's history", "When was John last promoted?", \
"Whose career has stalled for 4+ years?".

- Recommendation: Candidate ranking for a role with requirements \
and location. Example: "Recommend backend devs for a FinTech project \
in Chennai.", "Find best candidates for QA Lead in Pune.".

- TeamBuild: Assemble a multi-role team from a project brief. \
Example: "Build the best team for an AI healthcare project.", \
"Assemble a DevOps team."

- Promotion: Identify who is due for promotion. \
Example: "Who should we promote?", "Find employees ready for advancement."

- Transfer: Suggest internal department transfers. \
Example: "Suggest internal moves.", "Who could transfer to Engineering?"

- Attrition: Identify attrition-risk indicators. \
Example: "Who is at risk of leaving?", "Flag attrition-prone employees."

- SkillGap: Skill-gap analysis and hiring-cost estimation. \
Example: "What skills are we missing for a new AI centre in Hyderabad?", \
"Grow the AI division 40% under budget."

- Insights: Workforce scorecard with history-backed metrics. \
Example: "Give me the workforce scorecard.", \
"What is the fastest growing department?".

- Planner: Multi-step / executive questions that combine agents. \
Use this when the question clearly needs TWO OR MORE of the above \
agents and one single agent cannot answer it alone. \
Example: "We're opening an AI research centre in Hyderabad; \
recommend transfers, find skill gaps, estimate hiring cost, and \
summarize.", "How hiring trends correlated with promotion trends?"

Respond with a JSON object containing exactly three keys:
{"intent": "<one of the thirteen>", "reasoning": "<why>", "confidence": <0.0-1.0>}

Do NOT include any text outside the JSON object.
"""


class AIRouter:
    """
    Classifies user messages into structured routing decisions.

    The router is stateless — all conversation context is passed
    explicitly.
    """

    def __init__(
        self,
        llm: GroqLLM,
        logger: Logger,
    ) -> None:
        self._llm = llm
        self._logger = logger

    def classify(
        self,
        message: str,
        *,
        context: List[Dict[str, str]] | None = None,
    ) -> RouterDecision:
        """
        Classify a user message into an intent.

        Args:
            message: The user's input text.
            context: Optional prior conversation turns.

        Returns:
            A structured decision with intent, reasoning, and confidence.

        Raises:
            ServiceError: If classification fails.
        """
        start = time.perf_counter()
        op = "router.classify"

        try:
            messages = self._llm.build_messages(
                system_prompt=ROUTER_SYSTEM_PROMPT,
                user_message=message,
                context=context,
            )

            raw = self._llm.generate(
                messages,
                temperature=0.1,
                max_tokens=256,
            ).strip()

            decision = self._parse_decision(raw)

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | intent=%s | confidence=%.2f | %.1fms | %s",
                op,
                decision.intent.value,
                decision.confidence,
                duration_ms,
                decision.reasoning,
            )

            return decision

        except LlmError:
            raise ServiceError("LLM classification failed.") from None

        except ServiceError:
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s",
                op,
                duration_ms,
                exc,
            )
            raise ServiceError("Failed to classify request.") from exc

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _parse_decision(raw: str) -> RouterDecision:
        """
        Parse the LLM's JSON response into a RouterDecision.

        Args:
            raw: JSON string from the LLM.

        Returns:
            Parsed decision.

        Raises:
            ServiceError: If parsing fails or the intent is unknown.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            data: Dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ServiceError(
                f"Failed to parse router response: {exc}"
            ) from exc

        intent_str = data.get("intent", "").strip()

        try:
            intent = IntentType(intent_str)
        except ValueError:
            raise ServiceError(
                f"Unknown intent '{intent_str}'. "
                f"Must be one of {[e.value for e in IntentType]}."
            )

        return RouterDecision(
            intent=intent,
            reasoning=data.get("reasoning", ""),
            confidence=min(max(float(data.get("confidence", 0.0)), 0.0), 1.0),
        )
