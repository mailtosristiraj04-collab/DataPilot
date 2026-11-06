from dataclasses import dataclass

from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    principal_id: str


def get_current_principal(settings: Settings = Depends(get_settings)) -> Principal:
    if settings.auth_mode != "single_user_dev":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authenticated principal integration is not configured",
        )
    return Principal(principal_id=settings.dev_principal_id)


def require_owner(owner_id: str, principal: Principal) -> None:
    if owner_id != principal.principal_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
