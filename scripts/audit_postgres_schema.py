"""Read-only PostgreSQL/schema audit for MundoMix production.

Usage:
    flask --app wsgi shell
    python scripts/audit_postgres_schema.py

The script never creates, alters or drops database objects. It compares SQLAlchemy's
current model metadata with the live database and highlights Cloudinary references and
Alembic's recorded revision.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import inspect, text

# Make direct execution from the repository root work without modifying PYTHONPATH.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import *  # noqa: F401,F403,E402


CLOUDINARY_COLUMNS = {
    "product": ["cloudinary_public_id", "additional_image_public_ids"],
    "category": ["cloudinary_public_id"],
    "banner": ["cloudinary_public_id"],
    "restaurant": ["logo_cloudinary_public_id", "banner_cloudinary_public_id"],
    "restaurant_product": ["cloudinary_public_id"],
}


def main() -> int:
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())
        model_tables = {table.name: table for table in db.metadata.sorted_tables}

        print("=== MundoMix PostgreSQL schema audit (READ ONLY) ===")
        print(f"Database dialect: {db.engine.dialect.name}")
        print()

        print("-- Alembic version --")
        if "alembic_version" not in actual_tables:
            print("MISSING: alembic_version")
        else:
            rows = db.session.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars().all()
            print("version(s):", ", ".join(rows) if rows else "<empty>")
        print()

        missing_total = 0
        print("-- Model vs live database --")
        for table_name, table in model_tables.items():
            if table_name not in actual_tables:
                print(f"MISSING TABLE: {table_name}")
                missing_total += len(table.columns)
                continue
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing = [column.name for column in table.columns if column.name not in actual_columns]
            if missing:
                missing_total += len(missing)
                print(f"MISSING COLUMNS [{table_name}]: {', '.join(missing)}")

        print()
        print("-- Cloudinary columns --")
        for table_name, expected in CLOUDINARY_COLUMNS.items():
            if table_name not in actual_tables:
                print(f"{table_name}: TABLE MISSING")
                continue
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            for column in expected:
                status = "PASS" if column in actual else "MISSING"
                print(f"{status}: {table_name}.{column}")

        print()
        print("-- Live tables not represented by current SQLAlchemy metadata --")
        extra_tables = sorted(actual_tables - set(model_tables) - {"alembic_version"})
        print(", ".join(extra_tables) if extra_tables else "<none>")

        print()
        print(f"Schema audit result: {'FAIL' if missing_total else 'PASS'}")
        return 1 if missing_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
