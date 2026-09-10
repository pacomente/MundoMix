import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _path_from_base(value: str | None, default: Path) -> str:
    """Return an absolute filesystem path without depending on cwd."""
    if not value:
        return str(default.resolve())
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path.resolve())


def _database_uri() -> str:
    """Normalize local SQLite paths so Gunicorn can start from any cwd."""
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        db_path = (BASE_DIR / "instance" / "mundomix.db").resolve()
        return f"sqlite:///{db_path.as_posix()}"

    # Keep non-SQLite URLs untouched so a future database migration remains possible.
    if not value.startswith("sqlite:///"):
        return value

    raw_path = value[len("sqlite:///"):]
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return f"sqlite:///{path.resolve().as_posix()}"


class Config:
    ENVIRONMENT = os.getenv("FLASK_ENV", "development").strip().lower()
    DEBUG = os.getenv("FLASK_DEBUG", "1" if ENVIRONMENT != "production" else "0") == "1"
    TESTING = False

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite benefits from a short connection timeout when another worker is writing.
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}

    UPLOAD_FOLDER = _path_from_base(os.getenv("UPLOAD_FOLDER"), BASE_DIR / "uploads")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies are enabled by default in production. For a direct local HTTP
    # production-mode test, set SESSION_COOKIE_SECURE=0 in .env.
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE", "1" if ENVIRONMENT == "production" else "0"
    ) == "1"
