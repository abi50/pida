from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    app_name: str = "PIDA - Personal Intrusion Detection Agent"
    debug: bool = False
    db_path: str = str(BASE_DIR / "db" / "pida.db")
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8765"]
    input_poll_interval: float = 5.0
    session_poll_interval: float = 30.0

    model_config = {"env_file": ".env", "env_prefix": "PIDA_"}


settings = Settings()
