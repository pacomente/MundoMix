"""Safely migrate the existing MundoMix SQLite database to PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --sqlite instance/mundomix.db

The script always creates a timestamped SQLite backup before reading it.
It never deletes or modifies the SQLite source. By default it refuses to write
into a PostgreSQL database that already contains MundoMix rows, which avoids
accidental duplication. Use --allow-existing-target only after inspecting the
PostgreSQL database and understanding the consequences.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
DEFAULT_SQLITE = BASE_DIR / "instance" / "mundomix.db"
BACKUP_DIR = BASE_DIR / "backup"

# Parent tables first; dependent tables follow.
TABLE_ORDER = ["category", "admin", "banner", "setting", "product", "order", "order_item"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MundoMix: SQLite -> PostgreSQL")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="SQLite database path")
    parser.add_argument(
        "--allow-existing-target",
        action="store_true",
        help="Allow inserting into a target that already has rows",
    )
    return parser.parse_args()


def postgres_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    if not url.startswith("postgresql"):
        raise RuntimeError(
            "DATABASE_URL debe apuntar a PostgreSQL, por ejemplo "
            "postgresql+psycopg://usuario:password@host:5432/mundomix"
        )
    return url


def backup_sqlite(source: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"mundomix_{stamp}.db"
    shutil.copy2(source, target)
    return target


def sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return {row[0] for row in rows}


def sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def convert_value(value: Any, column_type: Any) -> Any:
    if value is None:
        return None
    type_name = column_type.__class__.__name__.lower()
    if "boolean" in type_name:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "si"}
        return bool(value)
    if "integer" in type_name or "bigint" in type_name:
        return int(value)
    if "numeric" in type_name or "decimal" in type_name:
        return Decimal(str(value))
    if "datetime" in type_name:
        if isinstance(value, datetime):
            return value
        raw = str(value).strip()
        if not raw:
            return None
        raw = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    pass
            raise ValueError(f"No se pudo convertir DateTime: {value!r}")
    if "date" in type_name and not "datetime" in type_name:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value).strip())
    return value


def scalar(engine, sql: str, params: dict[str, Any] | None = None) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar_one()


def main() -> int:
    args = parse_args()
    source = Path(args.sqlite).expanduser()
    if not source.is_absolute():
        source = (BASE_DIR / source).resolve()
    if not source.exists():
        raise FileNotFoundError(f"No existe la SQLite indicada: {source}")

    url = postgres_url()
    backup = backup_sqlite(source)
    print(f"Backup SQLite creado: {backup}")

    # Import after validating the source/target so a bad configuration fails before writes.
    from models import Admin, Banner, Category, Order, OrderItem, Product, Setting

    target_engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    )
    model_tables = {
        "category": Category.__table__,
        "product": Product.__table__,
        "order": Order.__table__,
        "order_item": OrderItem.__table__,
        "admin": Admin.__table__,
        "banner": Banner.__table__,
        "setting": Setting.__table__,
    }

    with target_engine.connect() as conn:
        missing_target = [
            table for table in TABLE_ORDER
            if conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = :table"),
                {"table": table},
            ).scalar() is None
        ]
    if missing_target:
        raise RuntimeError(
            "El PostgreSQL destino no tiene las tablas necesarias: " + ", ".join(missing_target) +
            ". Ejecutá primero `flask --app wsgi db upgrade`; este script no crea ni modifica el esquema con create_all()."
        )

    with target_engine.begin() as conn:
        if not args.allow_existing_target:
            existing = []
            for table in TABLE_ORDER:
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
                if count:
                    existing.append(f"{table}={count}")
            if existing:
                raise RuntimeError(
                    "El destino PostgreSQL ya contiene datos: " + ", ".join(existing) +
                    ". Por seguridad la migración se detuvo. Usá --allow-existing-target solo si corresponde."
                )

        with sqlite3.connect(source) as src:
            src.row_factory = sqlite3.Row
            available = sqlite_tables(src)
            missing = [t for t in TABLE_ORDER if t not in available]
            if missing:
                print("Advertencia: faltan tablas SQLite y se omitirán: " + ", ".join(missing))

            # Fail rather than silently discard columns that existed in the source.
            # This is important for a no-data-loss migration: if the SQLite schema
            # contains application columns that the current SQLAlchemy models do not
            # know about, the migration must be reviewed instead of ignoring them.
            model_column_names = {
                table: {column.name for column in model_table.columns}
                for table, model_table in model_tables.items()
            }
            unexpected = {}
            for table_name in TABLE_ORDER:
                if table_name not in available:
                    continue
                source_only = sorted(sqlite_columns(src, table_name) - model_column_names[table_name])
                if source_only:
                    unexpected[table_name] = source_only
            if unexpected:
                details = "; ".join(f"{table}: {', '.join(cols)}" for table, cols in unexpected.items())
                raise RuntimeError(
                    "La SQLite contiene columnas que no existen en los modelos actuales. "
                    "Para evitar pérdida de datos, la migración se detuvo: " + details
                )

            migrated: dict[str, int] = {}
            for table_name in TABLE_ORDER:
                if table_name not in available:
                    migrated[table_name] = 0
                    continue
                target = model_tables[table_name]
                source_cols = sqlite_columns(src, table_name)
                target_cols = {c.name: c for c in target.columns}
                common = [c.name for c in target.columns if c.name in source_cols]

                required_missing = [
                    c.name for c in target.columns
                    if c.name not in source_cols and not c.nullable and c.default is None and c.server_default is None
                ]
                if required_missing:
                    raise RuntimeError(
                        f"La tabla {table_name} no contiene columnas obligatorias requeridas por MundoMix: "
                        + ", ".join(required_missing)
                    )

                rows = src.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in common)} FROM "{table_name}"').fetchall()
                migrated[table_name] = 0
                if not rows:
                    continue

                for row in rows:
                    payload = {}
                    for col_name in common:
                        payload[col_name] = convert_value(row[col_name], target_cols[col_name].type)
                    # Fill newly introduced columns only when the model has a safe scalar Python default.
                    for col in target.columns:
                        if col.name in payload or col.default is None:
                            continue
                        default = col.default.arg
                        if callable(default):
                            # Current MundoMix defaults are deterministic except timestamps.
                            try:
                                payload[col.name] = default(None)
                            except TypeError:
                                payload[col.name] = default()
                        else:
                            payload[col.name] = default
                    names = list(payload)
                    quoted = ", ".join(f'"{n}"' for n in names)
                    placeholders = ", ".join(f":p{i}" for i in range(len(names)))
                    conn.execute(
                        text(f'INSERT INTO "{table_name}" ({quoted}) VALUES ({placeholders})'),
                        {f"p{i}": payload[n] for i, n in enumerate(names)},
                    )
                    migrated[table_name] += 1

    # PostgreSQL sequences must move past imported IDs.
    with target_engine.begin() as conn:
        for table_name in TABLE_ORDER:
            if table_name not in model_tables:
                continue
            max_id = conn.execute(text(f'SELECT MAX(id) FROM "{table_name}"')).scalar_one()
            if max_id is None:
                continue
            sequence = conn.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": table_name},
            ).scalar_one()
            if sequence:
                conn.execute(
                    text("SELECT setval(:sequence_name, :max_id, true)"),
                    {"sequence_name": sequence, "max_id": max_id},
                )

    # Compare source/target counts after migration.
    with sqlite3.connect(source) as src:
        available = sqlite_tables(src)
        sqlite_counts = {
            t: (src.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] if t in available else 0)
            for t in TABLE_ORDER
        }
    pg_counts = {
        t: scalar(target_engine, f'SELECT COUNT(*) FROM "{t}"')
        for t in TABLE_ORDER
    }

    print("\nMIGRACIÓN MUNDOMIX")
    print("==================")
    print(f"SQLite: {source}")
    print(f"Backup: {backup}")
    print("\nTabla          SQLite   PostgreSQL")
    print("---------------------------------")
    for table in TABLE_ORDER:
        print(f"{table:<14}{sqlite_counts[table]:>6}   {pg_counts[table]:>10}")
        if sqlite_counts[table] != pg_counts[table]:
            raise RuntimeError(f"Cantidad de registros distinta en {table}.")
    print("\nResultado: OK — cantidades de registros coinciden.")
    print("SQLite original: preservada y sin modificaciones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
