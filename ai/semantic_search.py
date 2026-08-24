"""
Semantic search agent.

RAG pipeline: user query → embed → vector search in Supabase via
pgvector → top matches → LLM generates a natural-language answer.

The agent now ALSO emits scored, itemized ``Explanation`` objects
alongside its natural-language answers so callers can answer
"why did you recommend X?" with itemized, weighted reasons.
"""

from __future__ import annotations

import json
import time
from logging import Logger
from typing import Any, Dict, List

from database.queries import EmbeddingRepository
from models.history import Explanation, ExplanationReason
from utils.exceptions import EmbeddingError, ExplanationError, LlmError, ServiceError

from .embeddings import EmbeddingGenerator
from .llm import GroqLLM

SEMANTIC_SYSTEM_PROMPT = """\
You are an HR assistant. The user asked to find employees by \
meaning. Below are the top matching employees from a semantic \
search, ordered by relevance (highest match first).

Results:
{results}

Write a concise natural-language answer. Mention the employee \
names and what makes them relevant. If there are no results, \
say so clearly. Use 1-4 sentences.
"""


EXPLAIN_PROMPT = """\
You are an HR assistant. A user asked why a specific employee \
was returned as a match for a semantic-search query.

User query: {query}
Employee: {employee_no} ({employee_name})
Similarity score: {similarity:.2f}
Available metadata: {metadata}

Write a short (1-3 sentence) plain-English explanation of why \
this employee was a good match. Be specific and factual. Do NOT \
use JSON or markdown headings.
"""


# Default weights used to build an :class:`Explanation`.
_WEIGHT_SIMILARITY = 0.7
_WEIGHT_TERM_OVERLAP = 0.3


class SemanticSearchAgent:
    """
    Finds employees by meaning, not by keywords.

    Pipeline:
        1. Embed the user's query.
        2. Search pgvector via Supabase for similar employees.
        3. Use the LLM to write a natural-language answer.

    Optionally (Scope 3) returns itemized ``Explanation`` objects
    so the caller can answer "why did you recommend X?".
    """

    def __init__(
        self,
        embedder: EmbeddingGenerator,
        embedding_repo: EmbeddingRepository,
        llm: GroqLLM,
        logger: Logger,
    ) -> None:
        self._embedder = embedder
        self._embedding_repo = embedding_repo
        self._llm = llm
        self._logger = logger

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Embed the query and return raw vector search results.

        Args:
            query: Natural-language search query.
            top_k: Max number of results.
            threshold: Minimum similarity (0-1).

        Returns:
            List of matching employee records with similarity.

        Raises:
            ServiceError: On failure.
        """
        start = time.perf_counter()
        op = "semantic_search.search"

        try:
            results = []
            try:
                query_vector = self._embedder.embed_query(query)
                results = self._embedding_repo.search(
                    query_vector,
                    match_threshold=threshold,
                    match_count=top_k,
                )
            except Exception as e:
                self._logger.warning("Vector database search failed, attempting keyword fallback: %s", e)

            if not results:
                # Fallback to local keyword/text matching across database profiles
                try:
                    from database.queries import EmployeeRepository
                    emp_repo = EmployeeRepository()
                    joined_select = (
                        "*,employee_profiles(*),contact_info(*),addresses(*),employment_details(*),position_history(*,departments(*))"
                    )
                    response = self._embedding_repo._execute(
                        self._embedding_repo.client.table("employees").select(joined_select)
                    )
                    if response.data:
                        from database.queries.sql_query_repository import SqlQueryRepository
                        sql_repo = SqlQueryRepository()
                        all_flat = [sql_repo._flatten_employee_row(r) for r in response.data]
                        
                        import re
                        query_clean = re.sub(r"[^\w\s]", " ", query.lower())
                        words = [w for w in query_clean.split() if w not in (
                            "who", "is", "in", "the", "department", "works", "with", "a", "an", "at", "for", "of", "all", "employee", "employees"
                        )]
                        
                        matched = []
                        for flat_row in all_flat:
                            score = 0
                            full_text = " ".join([
                                str(flat_row.get("full_name") or ""),
                                str(flat_row.get("department_name") or ""),
                                str(flat_row.get("position_title") or ""),
                                str(flat_row.get("city") or ""),
                                str(flat_row.get("employment_type") or ""),
                                str(flat_row.get("status") or ""),
                            ]).lower()
                            
                            # Support composite exact matches if words exist
                            for word in words:
                                if word in full_text:
                                    score += 1
                                    
                            if score > 0:
                                similarity = min(0.6 + (score * 0.1), 0.95)
                                matched.append({
                                    "employee_no": flat_row.get("employee_no"),
                                    "similarity": similarity,
                                    "full_name": flat_row.get("full_name"),
                                    "department": flat_row.get("department_name"),
                                    "position_title": flat_row.get("position_title"),
                                    "metadata": flat_row,
                                    "content": f"Employee {flat_row.get('full_name')} working as {flat_row.get('position_title')} in {flat_row.get('department_name')} department.",
                                })
                        
                        matched.sort(key=lambda x: x["similarity"], reverse=True)
                        results = matched[:top_k]
                except Exception as ex:
                    self._logger.warning("Local semantic search fallback failed: %s", ex)

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | query='%s' | hits=%d | %.1fms",
                op, query, len(results), duration_ms,
            )
            return results

        except ServiceError:
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError(
                "Semantic search failed."
            ) from exc

    def search_scored(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Run the search and attach an :class:`Explanation` to every
        returned result.

        Each returned dict carries:
            - the original fields from the embedding repo
            - ``score``: overall score in ``[0, 1]`` (same value as
              ``similarity`` if reported by the DB)
            - ``explanation``: an :class:`Explanation`

        Args:
            query: Natural-language search query.
            top_k: Max number of results.
            threshold: Minimum similarity (0-1).

        Returns:
            List of scored result dicts, ordered by score desc.
        """
        start = time.perf_counter()
        op = "semantic_search.search_scored"

        try:
            raw_results = self.search(
                query, top_k=top_k, threshold=threshold,
            )
            query_terms = _tokenize(query)

            scored: List[Dict[str, Any]] = []
            for row in raw_results:
                similarity = self._extract_similarity(row)
                explanation = self._build_explanation(
                    query_terms=query_terms,
                    row=row,
                    similarity=similarity,
                    threshold=threshold,
                )
                enriched = dict(row)
                enriched["score"] = similarity
                enriched["explanation"] = explanation
                scored.append(enriched)

            # Re-sort by score desc in case the repo didn't.
            scored.sort(key=lambda d: d["score"], reverse=True)

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | query='%s' | scored=%d | %.1fms | OK",
                op, query, len(scored), duration_ms,
            )
            return scored

        except ServiceError:
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError(
                "Scored semantic search failed.",
            ) from exc

    def answer(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> str:
        """
        Full RAG pipeline: query → answer.

        Args:
            query: Natural-language search query.
            top_k: Max number of results.
            threshold: Minimum similarity.

        Returns:
            NL answer describing the matches.

        Raises:
            ServiceError: On failure.
        """
        start = time.perf_counter()
        op = "semantic_search.answer"

        try:
            results = self.search(
                query, top_k=top_k, threshold=threshold,
            )

            prompt = SEMANTIC_SYSTEM_PROMPT.format(
                results=json.dumps(results, indent=2, default=str),
            )
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": query},
            ]
            answer = self._llm.generate(
                messages, temperature=0.2, max_tokens=512,
            ).strip()

            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.info(
                "%s | query='%s' | %.1fms | OK",
                op, query, duration_ms,
            )
            return answer

        except EmbeddingError:
            raise ServiceError("Embedding generation failed.") from None

        except LlmError:
            raise ServiceError("LLM response failed.") from None

        except ServiceError:
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "%s | %.1fms | ERROR", op, duration_ms,
            )
            raise ServiceError(
                "Semantic search answer failed."
            ) from exc

    def answer_explained(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Scored answer variant: returns both the NL answer AND the
        list of scored results with explanations.

        Returns:
            Dict with keys ``answer`` (str) and ``results`` (list
            of scored dicts, as produced by :meth:`search_scored`).
        """
        scored = self.search_scored(
            query, top_k=top_k, threshold=threshold,
        )
        # Strip heavy explanation objects for the prompt — the LLM
        # only needs names and similarity.
        lite = [
            {
                "employee_no": r.get("employee_no"),
                "name": _coalesce(r.get("full_name"), r.get("name")),
                "department": r.get("department"),
                "position_title": r.get("position_title"),
                "similarity": r.get("score", 0.0),
            }
            for r in scored
        ]
        prompt = SEMANTIC_SYSTEM_PROMPT.format(
            results=json.dumps(lite, indent=2, default=str),
        )
        answer = self._llm.generate(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": query},
            ],
            temperature=0.2,
            max_tokens=512,
        ).strip()
        return {"answer": answer, "results": scored}

    def explain(
        self,
        query: str,
        employee_no: str,
        *,
        threshold: float = 0.5,
    ) -> Explanation:
        """
        Build the explanation for one specific employee relative to
        the query.

        Useful when the user explicitly asks "why did you recommend
        X?" — the caller re-runs a search, then this method returns
        the explanation.

        Args:
            query: Original user query.
            employee_no: Employee to explain.
            threshold: Search threshold to re-run with.

        Returns:
            :class:`Explanation` with itemized reasons.
        """
        results = self.search_scored(
            query,
            top_k=50,
            threshold=threshold,
        )
        for r in results:
            if r.get("employee_no") == employee_no:
                exp = r.get("explanation")
                if isinstance(exp, Explanation):
                    return exp
        # Not a hit — return an "empty" explanation with score 0.
        return Explanation(
            score=0.0,
            reasons=[
                ExplanationReason(
                    factor="Above threshold",
                    is_met=False,
                    weight=1.0,
                    detail=(
                        "Employee did not appear in the top results "
                        "for the query."
                    ),
                )
            ],
            summary=(
                f"Employee '{employee_no}' was not returned as a "
                f"match for the query."
            ),
        )

    # ----------------------------------------------------------------
    # Internal: explanation construction
    # ----------------------------------------------------------------

    def _build_explanation(
        self,
        *,
        query_terms: List[str],
        row: Dict[str, Any],
        similarity: float,
        threshold: float,
    ) -> Explanation:
        """
        Build an :class:`Explanation` from a search hit.
        """
        reasons: List[ExplanationReason] = []

        # Factor 1: vector similarity magnitude
        sim_band = _similarity_band(similarity)
        reasons.append(
            ExplanationReason(
                factor="Semantic similarity",
                is_met=similarity >= threshold,
                weight=_WEIGHT_SIMILARITY,
                detail=(
                    f"Embedding similarity {similarity:.2f}"
                    f" ({sim_band})."
                ),
            )
        )

        # Factor 2: lexical overlap of query terms with the row's
        # name/department/position fields.
        name = str(row.get("full_name") or row.get("name") or "")
        dept = str(row.get("department") or "")
        pos = str(row.get("position_title") or row.get("position") or "")
        text_blob = f"{name} {dept} {pos}".lower()
        if query_terms:
            matched = [
                t for t in query_terms if t in text_blob
            ]
            overlap_ratio = len(matched) / len(query_terms)
        else:
            matched = []
            overlap_ratio = 0.0
        reasons.append(
            ExplanationReason(
                factor="Query term overlap",
                is_met=overlap_ratio > 0,
                weight=_WEIGHT_TERM_OVERLAP,
                detail=(
                    f"{len(matched)}/{len(query_terms)} query "
                    f"terms appear in name/department/position."
                ) if query_terms else "No query terms to compare.",
            )
        )

        # Factor 3: above-threshold gate
        reasons.append(
            ExplanationReason(
                factor="Above threshold",
                is_met=similarity >= threshold,
                weight=0.0,
                detail=(
                    f"Similarity {similarity:.2f} "
                    f"vs threshold {threshold:.2f}."
                ),
            )
        )

        score = (
            similarity * _WEIGHT_SIMILARITY
            + overlap_ratio * _WEIGHT_TERM_OVERLAP
        )

        summary = (
            f"{name or 'Employee'} matched with an overall score "
            f"of {score:.2f} (semantic similarity "
            f"{similarity:.2f}, term overlap "
            f"{int(overlap_ratio * 100)}%)."
        )

        return Explanation(
            score=round(score, 4),
            reasons=reasons,
            summary=summary,
        )

    @staticmethod
    def _extract_similarity(row: Dict[str, Any]) -> float:
        """
        Pull the similarity score out of the repo row.

        pgvector-based RPCs typically name the column ``similarity``
        or ``score``. If absent we default to 0 and let the
        downstream band/report treat it as a low-confidence match.
        """
        for key in ("similarity", "score", "distance"):
            val = row.get(key)
            if val is None:
                continue
            try:
                # Distance (e.g. L2) — convert to similarity if it
                # looks like a distance (>1).
                v = float(val)
                if key == "distance":
                    return max(0.0, 1.0 - v) if v >= 0 else 0.0
                return max(0.0, min(1.0, v))
            except (TypeError, ValueError):
                continue
        return 0.0


# =====================================================================
# Module-level helpers
# =====================================================================


_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "with", "and", "or", "for", "to", "of", "in", "on",
    "by", "at", "from", "as", "that", "this", "these", "those",
    "who", "what", "which", "whom", "where", "when", "why", "how",
    "do", "does", "did", "has", "have", "had", "i", "we", "you",
    "they", "he", "she", "it", "me", "us", "them", "him", "her",
    "my", "our", "your", "their", "his", "its",
    "find", "show", "tell", "give", "list", "search", "looking",
    "someone", "person", "people", "employee", "employees",
    "experience", "experienced", "work", "working", "worked",
    "skill", "skills", "skilled", "with",
}


def _tokenize(query: str) -> List[str]:
    """
    Tokenize a query into lowercased meaningful terms (stop-word
    filtered, length >= 2).
    """
    tokens: List[str] = []
    for raw in query.split():
        cleaned = "".join(c for c in raw if c.isalnum()).lower()
        if len(cleaned) >= 2 and cleaned not in _STOP_WORDS:
            tokens.append(cleaned)
    return tokens


def _similarity_band(similarity: float) -> str:
    """Map a similarity score to a qualitative band."""
    if similarity >= 0.85:
        return "very strong"
    if similarity >= 0.7:
        return "strong"
    if similarity >= 0.5:
        return "moderate"
    if similarity >= 0.3:
        return "weak"
    return "very weak"


def _coalesce(*values) -> Any:
    """Return the first non-None argument, else ``None``."""
    for v in values:
        if v is not None:
            return v
    return None

