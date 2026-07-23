"""
Tests for ConversationMemory.
"""

from __future__ import annotations

from ai import ConversationMemory


class TestConversationMemory:
    def test_starts_empty(self):
        mem = ConversationMemory(max_turns=10)
        assert mem.turn_count == 0
        assert mem.get_context() == []

    def test_adds_turns(self):
        mem = ConversationMemory()
        mem.add_turn("user", "Hello")
        mem.add_turn("assistant", "Hi!", intent="SQL")
        assert mem.turn_count == 2
        assert mem.get_last_user_message() == "Hello"
        assert mem.last_intent() == "SQL"

    def test_get_context_returns_recent_turns(self):
        mem = ConversationMemory()
        mem.add_turn("user", "Q1")
        mem.add_turn("assistant", "A1")
        mem.add_turn("user", "Q2")
        context = mem.get_context(max_turns=2)
        assert len(context) == 2
        assert context[0]["content"] == "A1"
        assert context[1]["content"] == "Q2"

    def test_drops_oldest_when_exceeding_max(self):
        mem = ConversationMemory(max_turns=3)
        for i in range(5):
            mem.add_turn("user", f"Q{i}")
        assert mem.turn_count == 3
        assert mem.get_last_user_message() == "Q4"
        assert mem.get_context()[0]["content"] == "Q2"

    def test_clear_resets(self):
        mem = ConversationMemory()
        mem.add_turn("user", "Hello")
        mem.clear()
        assert mem.turn_count == 0
        assert mem.get_context() == []

    def test_last_intent_returns_none_when_empty(self):
        mem = ConversationMemory()
        assert mem.last_intent() is None

    def test_last_user_message_returns_none_when_empty(self):
        mem = ConversationMemory()
        assert mem.get_last_user_message() is None
