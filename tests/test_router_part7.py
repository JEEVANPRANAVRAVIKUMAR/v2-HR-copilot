"""
Tests confirming the new Part 7 intent types are accepted by the
router's ``_parse_decision``.

The existing ``TestClassifyHappyPath`` already tests CRUD, SQL,
SemanticSearch, Analytics, History. These tests just verify the
parser recognises the names for the new Part 6-7 intents.
"""

from __future__ import annotations

import pytest

from ai import AIRouter, IntentType


class TestParseNewIntents:
    def test_accepts_recommendation(self):
        dec = AIRouter._parse_decision(
            '{"intent":"Recommendation","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.RECOMMENDATION

    def test_accepts_teambuild(self):
        dec = AIRouter._parse_decision(
            '{"intent":"TeamBuild","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.TEAMBUILD

    def test_accepts_promotion(self):
        dec = AIRouter._parse_decision(
            '{"intent":"Promotion","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.PROMOTION

    def test_accepts_transfer(self):
        dec = AIRouter._parse_decision(
            '{"intent":"Transfer","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.TRANSFER

    def test_accepts_attrition(self):
        dec = AIRouter._parse_decision(
            '{"intent":"Attrition","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.ATTRITION

    def test_accepts_skillgap(self):
        dec = AIRouter._parse_decision(
            '{"intent":"SkillGap","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.SKILLGAP

    def test_accepts_insights(self):
        dec = AIRouter._parse_decision(
            '{"intent":"Insights","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.INSIGHTS

    def test_accepts_planner(self):
        dec = AIRouter._parse_decision(
            '{"intent":"Planner","reasoning":"x","confidence":0.8}'
        )
        assert dec.intent == IntentType.PLANNER

    def test_all_13_intents_listed(self):
        all_values = {i.value for i in IntentType}
        expected = {
            "CRUD", "SQL", "Analytics", "SemanticSearch",
            "History", "Recommendation", "TeamBuild",
            "Promotion", "Transfer", "Attrition",
            "SkillGap", "Insights", "Planner",
        }
        assert all_values == expected