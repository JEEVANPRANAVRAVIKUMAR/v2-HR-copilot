"""
Groq LLM client wrapper.

Provides a clean, configurable interface to Groq's API with
automatic retries and consistent error handling. No other
module should import groq directly.
"""

from __future__ import annotations

import logging
import time
from logging import Logger
from typing import Any, List

from groq import Groq

from utils.exceptions import LlmError


class GroqLLM:
    """
    Thread-safe wrapper around the Groq API client.

    Reads model and API key from the application Settings so
    secrets are never hardcoded.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        logger: Logger | None = None,
    ) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model
        self._logger = logger or logging.getLogger(__name__)

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def generate(
        self,
        messages: List[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        retry_count: int = 2,
    ) -> str:
        """
        Send messages to the LLM and return the text response.

        Args:
            messages: Chat messages (role/content dicts).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            retry_count: Number of retries on failure.

        Returns:
            The model's response text.

        Raises:
            LlmError: If all retries are exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(1 + retry_count):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content

                if content is None:
                    raise LlmError("LLM returned an empty response.")

                self._logger.debug(
                    "LLM call succeeded (model=%s, tokens=%s).",
                    self._model,
                    getattr(response.usage, "total_tokens", "?"),
                )
                return content

            except Exception as exc:
                last_exception = exc
                self._logger.warning(
                    "LLM call attempt %d failed: %s",
                    attempt + 1,
                    exc,
                )
                if attempt < retry_count:
                    time.sleep(2 ** attempt)

        raise LlmError(
            f"LLM call failed after {retry_count + 1} attempts."
        ) from last_exception

    # ----------------------------------------------------------------
    # Convenience builders
    # ----------------------------------------------------------------

    def build_messages(
        self,
        system_prompt: str,
        user_message: str,
        *,
        context: List[dict[str, str]] | None = None,
    ) -> List[dict[str, str]]:
        """
        Build a message list from parts.

        Args:
            system_prompt: System-level instruction.
            user_message: Current user input.
            context: Optional prior conversation turns.

        Returns:
            Message list ready for ``generate``.
        """
        messages: List[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": user_message})
        return messages

    @property
    def model(self) -> str:
        """The configured model identifier."""
        return self._model
