import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _as_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_base_url: str
    session_secret: str
    groq_api_key: str | None = field(repr=False)
    groq_model: str
    cookie_secure: bool
    allowed_origins: tuple[str, ...]
    seed_demo_data: bool
    demo_password: str
    agent_mode: str
    groq_triage_api_key: str | None = field(default=None, repr=False)
    session_hours: int = 12
    max_evidence_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    raw_database_url = os.getenv("DATABASE_URL", "sqlite:///./batchbridge.db")
    # Normalize hosted PostgreSQL URLs for the psycopg SQLAlchemy driver.
    if raw_database_url.startswith("postgres://"):
        raw_database_url = raw_database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif raw_database_url.startswith("postgresql://"):
        raw_database_url = raw_database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:8000,http://127.0.0.1:5173,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    )
    cookie_secure = _as_bool("COOKIE_SECURE", False)
    agent_mode = os.getenv("AGENT_MODE", "llm").lower()
    if agent_mode not in {"llm", "demo"}:
        raise RuntimeError("AGENT_MODE must be llm or demo")
    session_secret = os.getenv("SESSION_SECRET", "development-only-secret")
    if cookie_secure and session_secret == "development-only-secret":
        raise RuntimeError("SESSION_SECRET must be set when COOKIE_SECURE=true")
    return Settings(
        database_url=raw_database_url,
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
        session_secret=session_secret,
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_triage_api_key=os.getenv("GROQ_TRIAGE_API_KEY", "").strip() or None,
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        cookie_secure=cookie_secure,
        allowed_origins=origins,
        seed_demo_data=_as_bool("SEED_DEMO_DATA", True),
        demo_password=os.getenv("DEMO_PASSWORD", "EscaleraDemo2026!"),
        agent_mode=agent_mode,
    )


def agent_execution_mode(agent_type: str) -> str:
    if agent_type in {"traceability", "escalation"}:
        return "rules"
    return "llm" if get_settings().agent_mode == "llm" else "demo_rules"
