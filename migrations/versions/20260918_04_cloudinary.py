"""Add Cloudinary references without removing legacy image columns."""
from alembic import op
import sqlalchemy as sa

revision = "20260918_04_cloudinary"
down_revision = "20260915_03_printing"
branch_labels = None
depends_on = None


def _cols(table):
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()


def _add(table, column, type_, index=False):
    if column not in _cols(table):
        op.add_column(table, sa.Column(column, type_, nullable=True))
        if index:
            op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade():
    _add("product", "image_url", sa.String(1000))
    _add("product", "cloudinary_public_id", sa.String(255), True)
    _add("product", "additional_image_urls", sa.Text())
    _add("product", "additional_image_public_ids", sa.Text())

    _add("category", "image_url", sa.String(1000))
    _add("category", "cloudinary_public_id", sa.String(255), True)

    _add("banner", "image_url", sa.String(1000))
    _add("banner", "cloudinary_public_id", sa.String(255), True)

    _add("restaurant", "logo_url", sa.String(1000))
    _add("restaurant", "logo_cloudinary_public_id", sa.String(255), True)
    _add("restaurant", "banner_url", sa.String(1000))
    _add("restaurant", "banner_cloudinary_public_id", sa.String(255), True)

    _add("restaurant_product", "image_url", sa.String(1000))
    _add("restaurant_product", "cloudinary_public_id", sa.String(255), True)


def downgrade():
    # Deliberately non-destructive: legacy columns remain available for rollback/fallback.
    pass
