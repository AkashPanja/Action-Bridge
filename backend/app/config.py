import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# crypto.py reads APP_ENCRYPTION_KEY straight from os.environ, which pydantic
# never populates — without this, stored credentials break on a plain launch.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./doc_action_center.db"
    database_url_sync: str = "sqlite:///./doc_action_center.db"
    app_name: str = "Action Bridge API"
    debug: bool = True
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_minutes: int = 480
    setup_complete_file: str = ".setup-complete"
    upload_dir: str = "./uploads"
    frontend_url: str = "http://localhost:5173"
    app_encryption_key: str = ""
    file_store_dir: str = "./filestore"
    max_extract_file_mb: int = 25

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.database_url

    class Config:
        env_file = ".env"


settings = Settings()

# Allow override from .env
if os.getenv("DATABASE_URL"):
    settings.database_url = os.getenv("DATABASE_URL")
    settings.database_url_sync = (
        os.getenv("DATABASE_URL", "")
        .replace("+asyncpg", "")
        .replace("+aiosqlite", "")
    )
