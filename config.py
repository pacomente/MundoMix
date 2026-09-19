import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _database_uri() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    environment = os.getenv("FLASK_ENV", "development").strip().lower()
    if not value:
        if environment == "production":
            raise RuntimeError(
                "DATABASE_URL no está configurada. En producción MundoMix requiere PostgreSQL."
            )
        db_path = (BASE_DIR / "instance" / "mundomix.db").resolve()
        return f"sqlite:///{db_path.as_posix()}"
    if environment == "production" and value.startswith("sqlite:"):
        raise RuntimeError("DATABASE_URL apunta a SQLite pero producción requiere PostgreSQL.")
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("sqlite:///"):
        raw_path = value[len("sqlite:///"):]
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = BASE_DIR / path
        return f"sqlite:///{path.resolve().as_posix()}"
    return value


class Config:
    ENVIRONMENT = os.getenv("FLASK_ENV", "development").strip().lower()
    DEBUG = os.getenv("FLASK_DEBUG", "1" if ENVIRONMENT != "production" else "0") == "1"
    TESTING = False

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "5")),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}

    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "")

    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "").strip()
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip()

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE", "1" if ENVIRONMENT == "production" else "0"
    ) == "1"
    PREFERRED_URL_SCHEME = "https" if ENVIRONMENT == "production" else "http"
