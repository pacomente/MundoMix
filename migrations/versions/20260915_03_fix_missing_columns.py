"""fix missing columns for restaurant_product and order

Revision ID: 20260915_03
Revises: 20260915_02
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260915_03'
down_revision = '20260915_02'
branch_labels = None
depends_on = None

def upgrade():
    # Columnas faltantes en restaurant_product
    op.add_column("restaurant_product", sa.Column("previous_price", sa.Numeric(12, 2)))
    op.add_column("restaurant_product", sa.Column("sku", sa.String(80)))
    op.add_column("restaurant_product", sa.Column("stock", sa.Integer()))
    op.add_column("restaurant_product", sa.Column("stock_control", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("restaurant_product", sa.Column("label", sa.String(100)))
    op.add_column("restaurant_product", sa.Column("nutrition", sa.Text()))
    op.add_column("restaurant_product", sa.Column("prep_min", sa.Integer()))
    op.add_column("restaurant_product", sa.Column("prep_max", sa.Integer()))
    op.add_column("restaurant_product", sa.Column("is_combo", sa.Boolean(), server_default=sa.false(), nullable=False))

    # Columnas faltantes en order
    op.add_column("order", sa.Column("delivery_zone", sa.String(150)))
    op.add_column("order", sa.Column("delivery_fee", sa.Numeric(12, 2)))

def downgrade():
    op.drop_column("order", "delivery_fee")
    op.drop_column("order", "delivery_zone")

    op.drop_column("restaurant_product", "is_combo")
    op.drop_column("restaurant_product", "prep_max")
    op.drop_column("restaurant_product", "prep_min")
    op.drop_column("restaurant_product", "nutrition")
    op.drop_column("restaurant_product", "label")
    op.drop_column("restaurant_product", "stock_control")
    op.drop_column("restaurant_product", "stock")
    op.drop_column("restaurant_product", "sku")
    op.drop_column("restaurant_product", "previous_price")
