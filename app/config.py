"""Application settings, read from environment variables with safe defaults."""
import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        # Any SQLAlchemy URL works (e.g. postgresql+psycopg://user:pw@host/db).
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./certificates.db")
        # Folder where generated PDFs are saved.
        self.storage_dir: Path = Path(os.getenv("STORAGE_DIR", "./storage"))
        # Upper limit of recipients accepted in ONE request.
        self.max_recipients: int = int(os.getenv("MAX_RECIPIENTS", "1000"))


settings = Settings()
