"""
Conversation memory.

Tracks the history of user and assistant turns so follow-up
questions can reference prior context.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


class ConversationMemory:
    """
    Lightweight in-memory conversation history.

    Each turn stores role, content, detected intent, and a
    timestamp. Oldest turns are dropped when ``max_turns`` is
    exceeded.
    """

    def __init__(self, max_turns: int = 20) -> None:
        self._turns: List[Dict[str, Any]] = []
        self._max_turns = max_turns

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def add_turn(
        self,
        role: str,
        content: str,
        *,
        intent: str | None = None,
    ) -> None:
        """
        Record a conversation turn.

        Args:
            role: ``"user"`` or ``"assistant"``.
            content: The message text.
            intent: Intent label from the router (for assistant turns).
        """
        self._turns.append({
            "role": role,
            "content": content,
            "intent": intent,
            "timestamp": datetime.utcnow().isoformat(),
        })

        if len(self._turns) > self._max_turns:
            self._turns = self._turns[-self._max_turns:]

    def get_context(self, max_turns: int = 10) -> List[Dict[str, str]]:
        """
        Return recent turns formatted as an LLM message list.

        Args:
            max_turns: Number of recent turns to include.

        Returns:
            List of ``{"role": ..., "content": ...}`` dicts.
        """
        recent = self._turns[-max_turns:] if max_turns else self._turns
        return [
            {"role": t["role"], "content": t["content"]}
            for t in recent
        ]

    def get_last_user_message(self) -> str | None:
        """
        Return the most recent user message, if any.
        """
        for turn in reversed(self._turns):
            if turn["role"] == "user":
                return turn["content"]
        return None

    def last_intent(self) -> str | None:
        """
        Return the intent of the most recent assistant turn.
        """
        for turn in reversed(self._turns):
            if turn["role"] == "assistant" and turn.get("intent"):
                return turn["intent"]
        return None

    def clear(self) -> None:
        """Reset the conversation history."""
        self._turns.clear()

    @property
    def turn_count(self) -> int:
        """Total number of recorded turns."""
        return len(self._turns)

    @property
    def max_turns(self) -> int:
        """Maximum number of turns retained."""
        return self._max_turns
