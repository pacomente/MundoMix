"""Merge heads and add missing product columns."""
from alembic import op
import sqlalchemy as sa

# Unifica las dos ramas en conflicto
revision = "20260918_01_fix_merge_and_columns"
down_revision = ("20260915_01_restaurants", "20260915_03_printing")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    ins = sa.inspect(bind)
    tables = set(ins.get_table_names())

    # Agrega las columnas faltantes en la tabla product si no existen
    if "product" in tables:
        cols = {c["name"] for c in ins.get_columns("product")}
        if "cloudinary_public_id" not in cols:
            op.add_column("product", sa.Column("cloudinary_public_id", sa.String(255), nullable=True))
        if "additional_image_public_ids" not in cols:
            op.add_column("product", sa.Column("additional_image_public_ids", sa.Text(), nullable=True))


def downgrade():
    pass
