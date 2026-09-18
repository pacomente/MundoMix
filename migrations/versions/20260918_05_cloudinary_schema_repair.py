"""Repair Cloudinary reference columns that may be missing despite a recorded head.

This migration is intentionally idempotent. It exists because a production database can
have ``alembic_version`` at ``20260918_04_cloudinary`` while one or more ALTER TABLE
operations from that revision were never actually present in the database (for example
because the revision was marked/applied against a different database).

No existing data or legacy image columns are removed.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260918_05_cloudinary_schema_repair"
down_revision = "20260918_04_cloudinary"
branch_labels = None
depends_on = None


EXPECTED_COLUMNS = {
    "product": {
        "cloudinary_public_id": sa.String(255),
        "additional_image_public_ids": sa.Text(),
    },
    "category": {
        "cloudinary_public_id": sa.String(255),
    },
    "banner": {
        "cloudinary_public_id": sa.String(255),
    },
    "restaurant": {
        "logo_cloudinary_public_id": sa.String(255),
        "banner_cloudinary_public_id": sa.String(255),
    },
    "restaurant_product": {
        "cloudinary_public_id": sa.String(255),
    },
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    for table, columns in EXPECTED_COLUMNS.items():
        if table not in tables:
            # The preceding migrations own table creation. Do not create a table here:
            # doing so could hide a larger schema/deployment problem.
            continue

        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, column_type in columns.items():
            if name not in existing:
                op.add_column(table, sa.Column(name, column_type, nullable=True))


def downgrade():
    # Deliberately non-destructive. Legacy data and image references must remain intact.
    pass
