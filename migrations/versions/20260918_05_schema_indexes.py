"""Align model indexes that were missing from the historical migrations."""
from alembic import op
import sqlalchemy as sa

revision = "20260918_05_schema_indexes"
down_revision = "20260918_04_cloudinary"
branch_labels = None
depends_on = None


def _indexes(table):
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table)}


def _add(name, table, columns):
    if name not in _indexes(table):
        op.create_index(name, table, columns)


def upgrade():
    _add("ix_restaurant_accept_orders", "restaurant", ["accept_orders"])
    _add("ix_restaurant_category_restaurant_active", "restaurant_category", ["restaurant_id", "active"])
    _add("ix_order_scheduled_for", "order", ["scheduled_for"])
    _add("ix_printed_at", "order", ["printed_at"])
    _add("ix_restaurant_promotion_active", "restaurant_promotion", ["active"])


def downgrade():
    # Kept non-destructive to match MundoMix production policy.
    pass
