from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    auth_mode: str = "single_user_dev"
    dev_principal_id: str = "local-development-user"
    database_url: str
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def validate_auth_mode(self) -> None:
        if self.auth_mode == "single_user_dev" and self.app_env == "production":
            raise ValueError("single_user_dev authentication cannot be used in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_auth_mode()
    return settings
