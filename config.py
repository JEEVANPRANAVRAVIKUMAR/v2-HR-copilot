"""
Centralized application configuration.

This module is the single source of truth for all application
configuration. Settings are loaded from environment variables
using pydantic-settings and cached for the lifetime of the
application.
"""

from functools import lru_cache
from dotenv import load_dotenv


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
load_dotenv()

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # ==========================
    # Application
    # ==========================

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

    # ==========================
    # Groq
    # ==========================

    groq_api_key: str = Field(
        ...,
        alias="GROQ_API_KEY"
    )

    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        alias="GROQ_MODEL"
    )

    # ==========================
    # Supabase
    # ==========================

    supabase_url: str = Field(
        ...,
        alias="SUPABASE_URL"
    )

    supabase_key: str = Field(
        ...,
        alias="SUPABASE_KEY"
    )

    # ==========================
    # Embeddings
    # ==========================

    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application settings.

    The configuration is loaded only once and cached for
    the lifetime of the application.

    Returns:
        Settings: Validated application settings.
    """
    return Settings()