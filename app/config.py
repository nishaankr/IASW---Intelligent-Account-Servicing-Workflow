#setting up pydantic so we can read config from .env and have type validations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-5"

    database_url: str = "postgresql+psycopg2://iasw:iasw@localhost:55432/iasw"

    filenet_root: Path = Path("./filenet_storage")

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    approve_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    reject_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

settings.filenet_root.mkdir(parents=True, exist_ok=True)