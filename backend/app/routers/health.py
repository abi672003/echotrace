from fastapi import APIRouter
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.schemas import HealthOut, ProviderKeyStatus, ProviderStatus

router = APIRouter()


def _provider_status(key: str) -> ProviderKeyStatus:
    return "configured" if key else "missing"


def _db_status(database_url: str) -> str:
    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
    except Exception:
        return "error"
    return "ok"


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    settings = get_settings()
    return HealthOut(
        status="ok",
        db=_db_status(settings.DATABASE_URL),
        providers=ProviderStatus(
            regulations=_provider_status(settings.REGULATIONS_API_KEY.get_secret_value()),
            gemini=_provider_status(settings.GEMINI_API_KEY.get_secret_value()),
            groq=_provider_status(settings.GROQ_API_KEY.get_secret_value()),
        ),
    )
