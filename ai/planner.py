"""
Part 7 — Two-tier router + Multi-agent Planner.

Tier 1 (fast path): simple single-tool questions go straight to one
agent — unchanged, exactly as Parts 1-5 dispatch.

Tier 2 (planner): when a question needs multiple steps or agents
a planner decomposes it into an ordered plan of sub-tasks, calls
the needed agents, passes results between steps, and synthesises
ONE comprehensive answer.

Guardrails: max steps cap, partial-result fallback on sub-agent
failure, full plan logging.

The planner is stateless — all context is passed explicitly.
"""

from __future__ import annotations

import json
import time
from logging import Logger
from typing import Any, Dict, List, Optional

from utils.exceptions import LlmError, ServiceError

from .llm import GroqLLM


# ----------------------------------------------------------------
# Complexity detector
# ----------------------------------------------------------------

# Keywords / phrases that strongly suggest a multi-step question.
_COMPLEX_KEYWORDS: List[str] = [
    "first", "then", "after that", "finally",
    "also compare", "and also", "at the same time",
    "summarize", "combine", "consolidate",
    "open a new", "opening a new", "opening an",
    "build the best team for", "assemble a team",
    "grow the division", "grow the workforce",
    "executive report", "decision support",
    "recommend transfers", "internal mobility",
    "skill gap", "hiring cost", "hiring budget",
    "under budget", "within budget", "% under",
    "weigh options", "pros and cons",
    "multi-step", "multiple steps", "step by step",
    "compare", "trade-off", "tradeoff",
    "if possible", "if we can",
    "rank", "prioritize",
]


def is_complex(message: str) -> bool:
    """
    Lightweight heuristic — checks for multi-step / executive
    keywords. Returns True if the message is likely a Tier-2
    (multi-agent) query.

    Also counts tokens: messages with > 20 tokens (words) are
    treated as complex regardless of keywords.
    """
    lowered = message.lower()
    for kw in _COMPLEX_KEYWORDS:
        if kw in lowered:
            return True
    token_count = len(message.split())
    return token_count > 30


# ----------------------------------------------------------------
# Planner
# ----------------------------------------------------------------


DECOMPOSITION_PROMPT = """\
You are an HR AI orchestrator. The user has asked a complex,
multi-step question about the workforce. Your job is to break it
into an ordered plan of sub-tasks.

Available agents and what they can do:

- SQL: answer factual database questions (e.g. "who joined in
  2024?", "list everyone in Engineering")
- Analytics: statistical/aggregate questions (e.g. headcount,
  tenure, department breakdown)
- CRUD: lookup / create / update / deactivate employee records
- SemanticSearch: find employees by meaning/skills (e.g.
  "someone with Python experience")
- History: career timeline / stall detection (e.g. "show me
  Rahul's history", "whose career has stalled?")
- Recommendation: rank candidates for a role given requirements
  and location
- TeamBuild: assemble a multi-role team from a project brief
- Promotion: rank who is due for promotion
- Transfer: suggest internal department moves
- Attrition: identify attrition risk factors
- SkillGap: identify skill gaps and estimate hiring cost
- Insights: history-backed workforce scorecard (fastest growing
  dept, largest hub, understaffed, hiring forecast)

Return a JSON object:

{{
  "summary": "<1-line summary of the plan>",
  "steps": [
    {{
      "step": 1,
      "agent": "<agent name from above list>",
      "sub_question": "<the specific sub-question to ask that agent>",
      "purpose": "<why this step is needed>",
      "depends_on_output_of": <previous-step-number or null>,
      "note": "<optional clarification on response>"
    }},
    ...
  ],
  "max_steps": <integer <= 5>
}}

Rules:
1. Each step must name one of the agents above EXACTLY.
2. Steps must be ordered — step 2 cannot depend on step 5.
3. Max 5 steps.
4. If the question is simple and can be answered by ONE agent,
   return {{"summary": "...", "steps": [{{"step":1,"agent":"<one>",
   "sub_question":"<the full original question>",
   "purpose":"answer directly","depends_on_output_of":null}}],
   "max_steps":1}}
5. The final step should always synthesize/narrate the answer.

Return ONLY the JSON — no markdown, no explanation.
"""

SYNTHESIS_PROMPT = """\
You are an HR executive assistant. The user asked a multi-step
question and below is the PLAN executed along with each step's
result.

Original question: {question}

Plan executed:
{plan_text}

Step results:
{step_results}

Write a comprehensive, well-structured plain-English answer that:

1. Summarises the answer to the original question.
2. References key numbers from the results.
3. Calls out recommendations clearly.
4. If any step failed, gracefully mention that it was skipped.
5. Makes the answer executive-ready: short sections, bullet-like
   phrasing where helpful.

Avoid JSON, markdown headings, or speculation. Write in clear
paragraphs. 3-8 sentences.
"""

MAX_STEPS = 5


class Planner:
    """
    Decomposes complex questions, runs sub-agents, synthesises.

    The planner does NOT know about individual agent internals —
    it receives a registry (``Dict[str, callable]``) that maps
    agent names to functions. Each function is called with
    ``(message: str, context: List[dict], previous_results: List[dict])``
    and must return a ``str`` answer.
    """

    _RESULT_SEPARATOR = "\n⋅⋅⋅\n"

    def __init__(
        self,
        llm: GroqLLM,
        logger: Logger,
    ) -> None:
        self._llm = llm
        self._logger = logger

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def execute(
        self,
        message: str,
        *,
        agent_registry: Optional[Dict[str, Any]] = None,
        context: Optional[List[Dict[str, str]]] = None,
        max_steps: int = MAX_STEPS,
    ) -> Dict[str, Any]:
        """
        Run a full planning → execution → synthesis cycle.

        Args:
            message: The user's complex question.
            agent_registry: ``{agent_name: callable}`` mapping each
                agent name (matching the decomposition prompt) to a
                function ``f(message, context, prev_results) -> str``.
                If ``None`` or empty, the planner can only return a
                plan — not execute it.
            context: Prior conversation turns.
            max_steps: Safety cap; overrides the plan if it exceeds
                this.

        Returns:
            Dict:
            {
              'complex': bool,
              'tier': 1 or 2,
              'plan': [...],
              'step_results': [...],
              'answer': str,
              'failed_steps': [...],
            }
        """
        start = time.perf_counter()
        op = "planner.execute"

        try:
            if not agent_registry:
                agent_registry = {}

            # --- Complexity detection ---
            complex_flag = is_complex(message)
            if not complex_flag:
                return {
                    "complex": False,
                    "tier": 1,
                    "plan": [],
                    "step_results": [],
                    "answer": "",
                    "failed_steps": [],
                }

            # --- Decompose into plan ---
            plan = self._decompose(message, max_steps=max_steps)
            if not plan or len(plan) == 0:
                return {
                    "complex": False,
                    "tier": 1,
                    "plan": [],
                    "step_results": [],
                    "answer": "",
                    "failed_steps": [],
                    "note": "Planner could not decompose — falls back to Tier 1.",
                }

            # --- Execute steps ---
            step_results, failed_steps = self._execute_plan(
                plan, message, agent_registry, context or [],
            )

            self._logger.info(
                "%s | steps=%d ok=%d failed=%d | %.0fms | plan start",
                op, len(plan), len(step_results), len(failed_steps),
                (time.perf_counter() - start) * 1000,
            )

            # --- Synthesise final answer ---
            synthesis = self._synthesize(
                question=message,
                plan=plan,
                step_results=step_results,
                failed_steps=failed_steps,
            )

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | plan steps=%d synth=%dchars | %.1fms | OK",
                op, len(plan), len(synthesis), duration_ms,
            )

            return {
                "complex": True,
                "tier": 2,
                "plan": plan,
                "step_results": [
                    {
                        "step": s["step"],
                        "agent": s["agent"],
                        "sub_question": s["sub_question"],
                        "result": r,
                    }
                    for s, r in zip(plan, step_results)
                ] if step_results else [],
                "answer": synthesis,
                "failed_steps": [
                    {
                        "step": snum,
                        "agent": plan[snum - 1]["agent"]
                        if snum - 1 < len(plan)
                        else "?",
                        "error": err,
                    }
                    for snum, err in failed_steps.items()
                ] if failed_steps else [],
            }

        except LlmError:
            raise ServiceError("Planner LLM call failed.") from None
        except ServiceError:
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR: %s", op, duration_ms, exc,
            )
            raise ServiceError("Multi-agent planning failed.") from exc

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _decompose(
        self,
        message: str,
        max_steps: int = MAX_STEPS,
    ) -> List[Dict[str, Any]]:
        """
        Ask the LLM to decompose the message into a plan.
        Returns a list of step dicts.
        """
        prompt = DECOMPOSITION_PROMPT.format()
        msgs = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ]
        raw = self._llm.generate(
            msgs, temperature=0.1, max_tokens=512,
        ).strip()

        plan_data = self._parse_plan(raw)
        steps = plan_data.get("steps", [])

        # Safety cap.
        if len(steps) > max_steps:
            steps = steps[:max_steps]
            plan_data["steps"] = steps
            plan_data["max_steps"] = max_steps

        return steps

    def _execute_plan(
        self,
        plan: List[Dict[str, Any]],
        original_message: str,
        agent_registry: Dict[str, Any],
        context: List[Dict[str, str]],
    ) -> tuple[List[str], Dict[int, str]]:
        """
        Execute each plan step in order, passing previous results.

        Returns:
            (successful_results, failed_map) where successful_results
            is a list of answer strings (one per plan step, placeholder
            for failed steps) and failed_map is ``{step_num: error_msg}``.
        """
        results: List[str] = []
        failed_map: Dict[int, str] = {}
        prev_results: List[Dict[str, Any]] = []

        for step in plan:
            step_num = step.get("step", 0)
            agent_name = step.get("agent", "").strip()
            sub_q = step.get("sub_question", original_message)
            dep_on = step.get("depends_on_output_of")
            purpose = step.get("purpose", "")
            if not sub_q or sub_q == "?":
                sub_q = original_message

            fn = agent_registry.get(agent_name)
            if fn is None:
                failed_map[step_num] = (
                    f"Agent '{agent_name}' is not available."
                )
                results.append("(skipped)")
                # Still push a placeholder so the shape is consistent.
                prev_results.append(
                    {"step": step_num, "agent": agent_name, "result": "(skipped)"}
                )
                continue

            try:
                answer = fn(sub_q, context, prev_results)
                if not answer:
                    answer = f"(Agent '{agent_name}' returned empty.)"
                results.append(answer)
                prev_results.append(
                    {"step": step_num, "agent": agent_name, "result": answer}
                )
            except Exception as exc:
                self._logger.warning(
                    "Planner step %d (%s) failed: %s",
                    step_num, agent_name, exc,
                )
                failed_map[step_num] = str(exc)
                results.append(f"(Step failed: {exc})")
                prev_results.append(
                    {"step": step_num, "agent": agent_name, "result": f"(failed: {exc})"}
                )

        return results, failed_map

    def _synthesize(
        self,
        *,
        question: str,
        plan: List[Dict[str, Any]],
        step_results: List[str],
        failed_steps: Optional[Dict[int, str]] = None,
    ) -> str:
        """
        Use the LLM to produce one comprehensive executive answer.
        """
        if not step_results:
            return (
                "I planned a multi-step answer but no agents were "
                "available to execute it. Please try a simpler "
                "question or verify the agent configuration."
            )

        plan_lines = [
            f"Step {s.get('step')}: {s.get('agent')} → "
            f"\"{s.get('sub_question','?')}\""
            for s in plan
        ]
        plan_text = "\n".join(plan_lines)

        result_lines = [
            f"Step {s.get('step')} ({s.get('agent')}): {r}"
            for s, r in zip(plan, step_results)
        ]
        if failed_steps:
            for snum, err in failed_steps.items():
                result_lines.append(
                    f"Step {snum}: (FAILED: {err})"
                )
        result_text = "\n".join(result_lines)

        prompt = SYNTHESIS_PROMPT.format(
            question=question,
            plan_text=plan_text,
            step_results=result_text,
        )
        msgs = [{"role": "user", "content": prompt}]
        return self._llm.generate(
            msgs, temperature=0.2, max_tokens=768,
        ).strip()

    @staticmethod
    def _parse_plan(raw: str) -> Dict[str, Any]:
        """
        Parse the LLM's JSON plan. Strips markdown fences.
        On failure returns a fallback single-step plan.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            data = json.loads(cleaned)
            # Ensure steps is a list.
            if not isinstance(data.get("steps"), list):
                raise ValueError("not a list")
            return data
        except (json.JSONDecodeError, ValueError):
            # Fallback: a single-step plan so the caller doesn't
            # crash — it will just get a direct LLM answer.
            return {
                "summary": "single step",
                "steps": [
                    {
                        "step": 1,
                        "agent": "SQL",
                        "sub_question": raw,
                        "purpose": "answer directly",
                        "depends_on_output_of": None,
                    }
                ],
                "max_steps": 1,
            }