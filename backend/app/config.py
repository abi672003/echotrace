from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite:///./echotrace.db"
    ADMIN_TOKEN: SecretStr = SecretStr("")
    CORS_ORIGINS: str = "http://localhost:5173"

    REGULATIONS_API_KEY: SecretStr = SecretStr("")
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBED_DIM: int = 768
    GEMINI_CHAT_MODEL: str = "gemini-3.8-flash"
    GROQ_API_KEY: SecretStr = SecretStr("")
    GROQ_CHAT_MODEL: str = "openai/gpt-oss-120b"
    LLM_PRIMARY: Literal["groq", "gemini"] = "groq"

    SIM_EDGE: float = 0.86
    SIM_MEMBER: float = 0.82
    MIN_FAMILY: int = 3
    MIN_CAMPAIGN: int = 5
    MIN_WORDS: int = 25
    AI_SAMPLE_PER_FAMILY: int = 8
    AGENT_MAX_FAMILIES: int = 10
    AGENT_MAX_STEPS: int = 6
    INGEST_MAX_COMMENTS: int = 500
    REGULATIONS_REQS_PER_HOUR: int = 900
    LLM_REQS_PER_MINUTE: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
