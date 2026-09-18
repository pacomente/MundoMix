"""Centralize MundoMix image references in Cloudinary."""
from alembic import op
import sqlalchemy as sa

revision = "20260918_04_cloudinary"
down_revision = "20260915_03_printing"
branch_labels = None
depends_on = None


def _cols(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()


def _add(table, name, column):
    inspector = sa.inspect(op.get_bind())
    if name not in _cols(inspector, table):
        op.add_column(table, sa.Column(name, column))


def upgrade():
    # Existing image/path columns are deliberately preserved. New uploads write
    # their HTTPS URL into the same field and keep the Cloudinary public_id in
    # the new nullable reference columns. This makes the rollout non-destructive.
    _add("product", "cloudinary_public_id", sa.String(255))
    _add("product", "additional_image_public_ids", sa.Text())
    _add("category", "cloudinary_public_id", sa.String(255))
    _add("banner", "cloudinary_public_id", sa.String(255))
    _add("restaurant", "logo_cloudinary_public_id", sa.String(255))
    _add("restaurant", "banner_cloudinary_public_id", sa.String(255))
    _add("restaurant_product", "cloudinary_public_id", sa.String(255))


def downgrade():
    # Intentionally non-destructive. Old columns remain valid for legacy paths.
    pass
