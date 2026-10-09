"""
Centralized application configuration.

This module is the single source of truth for all application
configuration. Settings are loaded from environment variables
and cached for the lifetime of the application.
"""

from __future__ import annotations

import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

# Seamlessly load Streamlit Community Cloud secrets into os.environ if available
try:
    import streamlit as _st
    if hasattr(_st, "secrets"):
        for _k, _v in _st.secrets.items():
            if isinstance(_v, str) and _k not in os.environ:
                os.environ[_k] = _v
except Exception:
    pass

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field

    class Settings(BaseSettings):
        """Application settings loaded via pydantic-settings."""

        app_name: str = Field(
            default="Enterprise HR AI Assistant",
            alias="APP_NAME"
        )
        app_version: str = Field(
            default="2.0.0",
            alias="APP_VERSION"
        )
        log_level: str = Field(
            default="INFO",
            alias="LOG_LEVEL"
        )
        groq_api_key: str = Field(
            default_factory=lambda: os.getenv("GROQ_API_KEY", ""),
            alias="GROQ_API_KEY"
        )
        groq_model: str = Field(
            default="openai/gpt-oss-120b",
            alias="GROQ_MODEL"
        )
        supabase_url: str = Field(
            default_factory=lambda: os.getenv("SUPABASE_URL", ""),
            alias="SUPABASE_URL"
        )
        supabase_key: str = Field(
            default_factory=lambda: os.getenv("SUPABASE_KEY", ""),
            alias="SUPABASE_KEY"
        )
        embedding_model: str = Field(
            default="sentence-transformers/all-MiniLM-L6-v2",
            alias="EMBEDDING_MODEL"
        )

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            case_sensitive=False,
        )

except ImportError:
    try:
        from pydantic import BaseSettings, Field  # type: ignore

        class Settings(BaseSettings):  # type: ignore
            """Fallback pydantic v1 BaseSettings."""
            app_name: str = Field(default="Enterprise HR AI Assistant")
            app_version: str = Field(default="2.0.0")
            log_level: str = Field(default="INFO")
            groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
            groq_model: str = Field(default=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
            supabase_url: str = Field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
            supabase_key: str = Field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))
            embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")

            class Config:
                env_file = ".env"
                case_sensitive = False
                extra = "ignore"

    except (ImportError, Exception):
        from dataclasses import dataclass

        @dataclass
        class Settings:  # type: ignore
            """Pure Python dataclass fallback when pydantic is not installed."""
            app_name: str = os.getenv("APP_NAME", "Enterprise HR AI Assistant")
            app_version: str = os.getenv("APP_VERSION", "2.0.0")
            log_level: str = os.getenv("LOG_LEVEL", "INFO")
            groq_api_key: str = os.getenv("GROQ_API_KEY", "")
            groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            supabase_url: str = os.getenv("SUPABASE_URL", "")
            supabase_key: str = os.getenv("SUPABASE_KEY", "")
            embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application settings.

    The configuration is loaded only once and cached for
    the lifetime of the application.
    """
    return Settings()