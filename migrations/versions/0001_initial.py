"""Establish the MundoMix ecommerce schema without destructive recreation.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(bind, name):
    return inspect(bind).has_table(name)


def _create_index_if_missing(bind, name, table, columns):
    names = {idx["name"] for idx in inspect(bind).get_indexes(table)}
    if name not in names:
        op.create_index(name, table, columns, unique=False)


def upgrade():
    bind = op.get_bind()

    if not _has_table(bind, "category"):
        op.create_table(
            "category",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=140), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("image", sa.String(length=255), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
            sa.UniqueConstraint("slug"),
        )
    if not _has_table(bind, "admin"):
        op.create_table(
            "admin",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
        )
    if not _has_table(bind, "banner"):
        op.create_table(
            "banner",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=180), nullable=True),
            sa.Column("subtitle", sa.String(length=300), nullable=True),
            sa.Column("image", sa.String(length=255), nullable=True),
            sa.Column("button_text", sa.String(length=80), nullable=True),
            sa.Column("button_url", sa.String(length=300), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_table(bind, "setting"):
        op.create_table(
            "setting",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )
    if not _has_table(bind, "product"):
        op.create_table(
            "product",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("slug", sa.String(length=220), nullable=False),
            sa.Column("sku", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("price_delivery", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("price_pickup", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
            sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("image", sa.String(length=255), nullable=True),
            sa.Column("additional_images", sa.Text(), nullable=True),
            sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["category_id"], ["category.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
            sa.UniqueConstraint("sku"),
        )
    if not _has_table(bind, "order"):
        op.create_table(
            "order",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_name", sa.String(length=160), nullable=False),
            sa.Column("customer_phone", sa.String(length=40), nullable=False),
            sa.Column("fulfillment_method", sa.String(length=20), nullable=False),
            sa.Column("address", sa.String(length=300), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="Nuevo"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_table(bind, "order_item"):
        op.create_table(
            "order_item",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_name_snapshot", sa.String(length=180), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table(bind, "product"):
        _create_index_if_missing(bind, "ix_product_slug", "product", ["slug"])
        _create_index_if_missing(bind, "ix_product_sku", "product", ["sku"])
        _create_index_if_missing(bind, "ix_product_category_id", "product", ["category_id"])
    if _has_table(bind, "order"):
        _create_index_if_missing(bind, "ix_order_status", "order", ["status"])
        _create_index_if_missing(bind, "ix_order_created_at", "order", ["created_at"])
    if _has_table(bind, "order_item"):
        _create_index_if_missing(bind, "ix_order_item_order_id", "order_item", ["order_id"])


def downgrade():
    # This baseline is intentionally non-destructive. Production data must not
    # be removed by rolling back the initial schema migration.
    raise RuntimeError("0001_initial es una migración de adopción y no admite downgrade destructivo.")
