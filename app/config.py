"""Settings read from the environment (and from .env in the project root)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    admin_username: str
    admin_password: str
    secret_key: str
    data_dir: Path
    secure_cookies: bool = False
    session_max_age: int = 7 * 24 * 3600

    @property
    def db_path(self) -> Path:
        return self.data_dir / "maindb.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(PROJECT_DIR / ".env")
        missing = [name for name in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "SECRET_KEY") if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Missing settings in .env: {', '.join(missing)} (see .env.example)")
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        if not data_dir.is_absolute():
            data_dir = PROJECT_DIR / data_dir
        return cls(
            admin_username=os.environ["ADMIN_USERNAME"],
            admin_password=os.environ["ADMIN_PASSWORD"],
            secret_key=os.environ["SECRET_KEY"],
            data_dir=data_dir,
            secure_cookies=os.environ.get("SECURE_COOKIES", "").lower() in {"1", "true", "yes"},
        )
