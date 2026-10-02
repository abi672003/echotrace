from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    admin_token = settings.ADMIN_TOKEN.get_secret_value()
    if not admin_token:
        return
    if x_admin_token != admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Missing or invalid X-Admin-Token."},
        )
