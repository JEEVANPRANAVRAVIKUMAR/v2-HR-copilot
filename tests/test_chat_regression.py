"""Broad, deterministic regression coverage for the assistant chat boundary."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai import AIRouter, IntentType, Planner, is_complex


def _load_chat_functions() -> dict:
    """Load the page's pure chat functions without executing Streamlit UI code."""
    page = Path(__file__).parents[1] / "pages" / "1_assistant.py"
    tree = ast.parse(page.read_text(encoding="utf-8"))
    wanted = {
        "_agent_registry",
        "dispatch_message",
        "_extract_role",
        "_extract_location",
        "_format_scored_list",
        "json_dump_simple",
        "_format_currency",
        "_format_skill_gap",
    }
    body = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {"__name__": "chat_regression"}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(page), "exec"), namespace)
    return namespace


CHAT_FUNCTIONS = _load_chat_functions()


class _FakeMemory:
    def __init__(self) -> None:
        self.turns: list[tuple[str, str, str | None]] = []

    def get_context(self) -> list[dict[str, str]]:
        return [{"role": role, "content": content} for role, content, _ in self.turns]

    def add_turn(self, role: str, content: str, *, intent: str | None = None) -> None:
        self.turns.append((role, content, intent))


class _FakeAgent:
    def __init__(self, result=None) -> None:
        self.result = result

    def answer(self, *args, **kwargs):
        return self.result if self.result is not None else "answer"

    def answer_question(self, *args, **kwargs):
        return self.result if self.result is not None else "analytics"

    def process(self, *args, **kwargs):
        return self.result if self.result is not None else "processed"

    def analyze(self, *args, **kwargs):
        return self.result if self.result is not None else []

    def recommend(self, *args, **kwargs):
        return self.result if self.result is not None else []

    def build(self, *args, **kwargs):
        return self.result if self.result is not None else {"summary": "team"}

    def full_scorecard(self, *args, **kwargs):
        return self.result if self.result is not None else {}


class _FakeRouter:
    def classify(self, message, *, context=None):
        lowered = message.lower()
        mapping = [
            ("employee details", IntentType.CRUD),
            ("headcount", IntentType.ANALYTICS),
            ("skills", IntentType.SEMANTIC_SEARCH),
            ("joined", IntentType.SQL),
            ("history", IntentType.HISTORY),
            ("recommend", IntentType.RECOMMENDATION),
            ("team", IntentType.TEAMBUILD),
            ("promote", IntentType.PROMOTION),
            ("transfer", IntentType.TRANSFER),
            ("attrition", IntentType.ATTRITION),
            ("skill gap", IntentType.SKILLGAP),
            ("scorecard", IntentType.INSIGHTS),
        ]
        for marker, intent in mapping:
            if marker in lowered:
                return SimpleNamespace(intent=intent)
        return SimpleNamespace(intent=IntentType.CRUD)


class _FakePlanner:
    def execute(self, message, *, agent_registry, context):
        return {
            "complex": True,
            "answer": "planned answer",
            "plan": [{"step": 1, "agent": "SQL", "sub_question": message}],
        }


class _FakeStreamlit:
    def __init__(self, session_state):
        self.session_state = session_state


def _make_session_state():
    scored = [{"full_name": "Employee", "score": None}]
    scoreless = [{"full_name": "Employee"}]
    return SimpleNamespace(
        memory=_FakeMemory(),
        router=_FakeRouter(),
        planner=_FakePlanner(),
        is_complex=is_complex,
        sql_agent=_FakeAgent("sql"),
        crud_agent=_FakeAgent("crud"),
        semantic_agent=_FakeAgent("semantic"),
        analytics_agent=_FakeAgent("analytics"),
        history_agent=_FakeAgent("history"),
        recommendation_engine=_FakeAgent(scored),
        team_builder=_FakeAgent({"summary": "team"}),
        promotion_analyzer=_FakeAgent(scoreless),
        transfer_analyzer=_FakeAgent(scored),
        attrition_risk=_FakeAgent(scored),
        skill_gap_agent=_FakeAgent({}),
        insight_agent=_FakeAgent({}),
    )


def _questions() -> list[str]:
    bases = [
        "Show employee details for Rahul Sharma",
        "What is the headcount by department?",
        "Find employees with Python skills",
        "Who joined in 2024?",
        "Show Rahul's history",
        "Recommend backend developers in Chennai",
        "Build a team for the AI project",
        "Who should we promote?",
        "Suggest an internal transfer",
        "Who has attrition risk?",
        "What is the skill gap for Hyderabad?",
        "Give me the workforce scorecard",
        "Compare headcount and hiring trends, then summarize",
        "Show me all employees",
        "How many active employees are there?",
        "Find someone experienced in data engineering",
        "List everyone in Engineering",
        "When was Priya last promoted?",
        "Recommend QA leads for Pune",
        "Assemble a DevOps team",
        "Find employees ready to promote",
        "Who could transfer to Engineering?",
        "Flag attrition-prone employees",
        "What skills are missing for a new AI center?",
        "What is the fastest-growing department?",
    ]
    return [f"{base} (case {i})" for i in range(1, 5) for base in bases]


def test_one_hundred_chat_questions_do_not_raise_in_dispatch():
    session_state = _make_session_state()
    CHAT_FUNCTIONS["st"] = _FakeStreamlit(session_state)

    for question in _questions():
        response = CHAT_FUNCTIONS["dispatch_message"](question)
        assert isinstance(response, str), question
        assert response.strip(), question

    assert len(_questions()) == 100


@pytest.mark.parametrize("message", ["recommend ,", "recommend :", "recommend ..."])
def test_role_extraction_handles_punctuation_only_tokens(message):
    assert CHAT_FUNCTIONS["_extract_role"](message) == "Engineer"


def test_scored_list_handles_missing_and_null_scores():
    formatter = CHAT_FUNCTIONS["_format_scored_list"]
    assert "Employee" in formatter([{"full_name": "Employee"}])
    assert "Employee" in formatter([{"full_name": "Employee", "score": None}])


def test_json_dump_simple_handles_partial_scorecard():
    result = CHAT_FUNCTIONS["json_dump_simple"](
        {"fastest_growing": None, "largest_hub": None, "understaffed": None}
    )
    assert '"headcount": null' in result


def test_router_tolerates_malformed_optional_llm_fields():
    decision = AIRouter._parse_decision(
        '{"intent":"SQL","reasoning":null,"confidence":"not-a-number"}'
    )
    assert decision.intent == IntentType.SQL
    assert decision.reasoning == "None"
    assert decision.confidence == 0.0


def test_planner_tolerates_malformed_plan_shape_and_step_number():
    fallback = Planner._parse_plan("null")
    assert fallback["steps"][0]["agent"] == "SQL"

    planner = Planner.__new__(Planner)
    results, failures = planner._execute_plan(
        [{"step": "not-a-number", "agent": "SQL", "sub_question": "count"}],
        "count",
        {"SQL": lambda message, context, previous: "ok"},
        [],
    )
    assert results == ["ok"]
    assert failures == {}
