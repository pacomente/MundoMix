"""Gastronomía 2.0: modifiers, combos, promotions, delivery, scheduling and snapshots."""
from alembic import op
import sqlalchemy as sa

revision="20260915_02_gastronomia_20"
down_revision="20260915_01"
branch_labels=None
depends_on=None

def _cols(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()

def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    def addcol(table, name, type_, **kwargs):
        if name not in _cols(sa.inspect(op.get_bind()), table):
            op.add_column(table, sa.Column(name, type_, **kwargs))

    # Restaurant configuration.
    addcol("restaurant", "info", sa.Text())
    addcol("restaurant", "accept_orders", sa.Boolean(), server_default=sa.true(), nullable=False)
    addcol("restaurant", "pause_message", sa.String(300))
    addcol("restaurant", "delivery_enabled", sa.Boolean(), server_default=sa.true(), nullable=False)
    addcol("restaurant", "pickup_enabled", sa.Boolean(), server_default=sa.true(), nullable=False)
    addcol("restaurant", "delivery_fee", sa.Numeric(12, 2))
    addcol("restaurant", "minimum_order", sa.Numeric(12, 2))
    addcol("restaurant", "delivery_zones", sa.JSON())
    addcol("restaurant", "prep_min", sa.Integer())
    addcol("restaurant", "prep_max", sa.Integer())
    addcol("restaurant", "theme_color", sa.String(20))

    # Product configuration.
    addcol("restaurant_product", "previous_price", sa.Numeric(12, 2))
    addcol("restaurant_product", "stock_control", sa.Boolean(), server_default=sa.false(), nullable=False)
    addcol("restaurant_product", "display_order", sa.Integer(), server_default="0", nullable=False)
    addcol("restaurant_product", "label", sa.String(40))
    addcol("restaurant_product", "nutrition", sa.Text())
    addcol("restaurant_product", "prep_min", sa.Integer())
    addcol("restaurant_product", "prep_max", sa.Integer())
    addcol("restaurant_product", "is_combo", sa.Boolean(), server_default=sa.false(), nullable=False)

    # Order and snapshot fields.
    addcol("order", "delivery_zone", sa.String(160))
    addcol("order", "subtotal", sa.Numeric(12, 2))
    addcol("order", "discount", sa.Numeric(12, 2))
    addcol("order", "delivery_fee", sa.Numeric(12, 2))
    addcol("order", "scheduled_for", sa.DateTime())
    addcol("order_item", "modifiers_json", sa.Text(), server_default="[]", nullable=False)
    addcol("order_item", "item_note", sa.Text(), server_default="", nullable=False)

    # Defaults for existing rows.
    op.execute('UPDATE restaurant SET delivery_fee=0 WHERE delivery_fee IS NULL')
    op.execute('UPDATE restaurant SET minimum_order=0 WHERE minimum_order IS NULL')
    op.execute('UPDATE restaurant SET prep_min=20 WHERE prep_min IS NULL')
    op.execute('UPDATE restaurant SET prep_max=30 WHERE prep_max IS NULL')
    op.execute('UPDATE restaurant_product SET stock_control=TRUE WHERE stock > 0')
    op.execute('UPDATE restaurant_product SET display_order=0 WHERE display_order IS NULL')
    op.execute('UPDATE "order" SET subtotal=total WHERE subtotal IS NULL')
    op.execute('UPDATE "order" SET discount=0 WHERE discount IS NULL')
    op.execute('UPDATE "order" SET delivery_fee=0 WHERE delivery_fee IS NULL')
    op.execute("UPDATE order_item SET modifiers_json='[]' WHERE modifiers_json IS NULL")
    op.execute("UPDATE order_item SET item_note='' WHERE item_note IS NULL")

    # New normalized menu tables.
    if "modifier_group" not in tables:
        op.create_table(
            "modifier_group",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("min_choices", sa.Integer(), server_default="0", nullable=False),
            sa.Column("max_choices", sa.Integer(), server_default="1", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        )
        op.create_index("ix_modifier_group_restaurant_id", "modifier_group", ["restaurant_id"])
    if "modifier_option" not in tables:
        op.create_table(
            "modifier_option",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("modifier_group.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("price_delta", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        )
        op.create_index("ix_modifier_option_group_id", "modifier_option", ["group_id"])
    if "product_modifier_group" not in tables:
        op.create_table(
            "product_modifier_group",
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("restaurant_product.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("modifier_group.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        )
    if "combo_component" not in tables:
        op.create_table(
            "combo_component",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("combo_id", sa.Integer(), sa.ForeignKey("restaurant_product.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("restaurant_product.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        )
        op.create_index("ix_combo_component_combo_id", "combo_component", ["combo_id"])
        op.create_index("ix_combo_component_product_id", "combo_component", ["product_id"])
    if "restaurant_promotion" not in tables:
        op.create_table(
            "restaurant_promotion",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("promotion_type", sa.String(20), server_default="percentage", nullable=False),
            sa.Column("value", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("restaurant_product.id", ondelete="CASCADE"), nullable=True),
            sa.Column("min_quantity", sa.Integer(), server_default="2", nullable=False),
            sa.Column("starts_at", sa.DateTime()),
            sa.Column("ends_at", sa.DateTime()),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        )
        op.create_index("ix_restaurant_promotion_restaurant_id", "restaurant_promotion", ["restaurant_id"])
        op.create_index("ix_restaurant_promotion_product_id", "restaurant_promotion", ["product_id"])

def downgrade():
    pass
