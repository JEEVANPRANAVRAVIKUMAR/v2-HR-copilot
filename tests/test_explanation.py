"""
Tests for the shared :class:`Explanation` model.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.history import Explanation, ExplanationReason


class TestExplanationReason:
    def test_minimal_construction(self):
        r = ExplanationReason(factor="Skill match", is_met=True)
        assert r.factor == "Skill match"
        assert r.is_met is True
        assert r.weight == 1.0
        assert r.detail is None

    def test_full_construction(self):
        r = ExplanationReason(
            factor="Tenure",
            is_met=False,
            weight=0.4,
            detail="Only 1 year vs required 3",
        )
        assert r.weight == 0.4
        assert r.detail == "Only 1 year vs required 3"

    def test_factor_required(self):
        with pytest.raises(ValidationError):
            ExplanationReason(is_met=True)


class TestExplanation:
    def test_defaults(self):
        e = Explanation()
        assert e.score == 0.0
        assert e.reasons == []
        assert e.summary is None

    def test_with_reasons(self):
        e = Explanation(
            score=0.82,
            reasons=[
                ExplanationReason(factor="sim", is_met=True, weight=0.7),
                ExplanationReason(factor="terms", is_met=False, weight=0.3),
            ],
            summary="Strong match.",
        )
        assert e.score == 0.82
        assert len(e.reasons) == 2
        assert e.reasons[0].factor == "sim"
        assert e.summary == "Strong match."

    def test_serialization_roundtrip(self):
        e = Explanation(
            score=0.5,
            reasons=[ExplanationReason(factor="x", is_met=True)],
            summary="hi",
        )
        dumped = e.model_dump()
        rebuilt = Explanation.model_validate(dumped)
        assert rebuilt == e

    def test_json_roundtrip(self):
        e = Explanation(
            score=0.9,
            reasons=[ExplanationReason(factor="y", is_met=True, weight=0.5)],
        )
        s = e.model_dump_json()
        e2 = Explanation.model_validate_json(s)
        assert e2 == e


class TestExplanationSemantics:
    """
    Loose contract tests that pin the intended usage of an
    Explanation for any consumer.
    """

    def test_score_is_in_unit_interval(self):
        # Score must be expressible in [0, 1]; the model itself does
        # not enforce clamping (consumers compute it), but we use
        # the convention that 0..1 is the valid range.
        for s in (0.0, 0.25, 0.5, 0.75, 1.0):
            e = Explanation(score=s)
            assert 0.0 <= e.score <= 1.0

    def test_weighted_reasons_reflect_score(self):
        """A small computation showing how a consumer might combine
        the reason weights into the overall score."""
        reasons = [
            ExplanationReason(factor="sim", is_met=True, weight=0.7, detail="0.85 sim"),
            ExplanationReason(factor="terms", is_met=True, weight=0.3, detail="0.5 overlap"),
        ]
        # Pretend the underlying per-factor values were 0.85 and 0.5.
        underlying = {"sim": 0.85, "terms": 0.5}
        weighted_score = sum(
            underlying[r.factor] * r.weight for r in reasons
        ) / sum(r.weight for r in reasons)
        # 0.85*0.7 + 0.5*0.3 = 0.595 + 0.15 = 0.745 / 1.0 = 0.745
        assert weighted_score == pytest.approx(0.745)
