"""Add multi-commerce restaurant platform tables."""
from alembic import op
import sqlalchemy as sa

revision = "20260915_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # The original project historically created these core tables with
    # SQLAlchemy create_all().  The migration tree must also be able to build
    # a completely empty PostgreSQL database, so create them here when absent.
    if "category" not in tables:
        op.create_table(
            "category",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("slug", sa.String(140), nullable=False),
            sa.Column("description", sa.Text(), server_default=""),
            sa.Column("image", sa.String(255)),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.UniqueConstraint("name", name="uq_category_name"),
            sa.UniqueConstraint("slug", name="uq_category_slug"),
        )
        op.create_index("ix_category_slug", "category", ["slug"])

    if "admin" not in tables:
        op.create_table(
            "admin",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(120), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.UniqueConstraint("username", name="uq_admin_username"),
        )

    if "banner" not in tables:
        op.create_table(
            "banner",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(180), server_default=""),
            sa.Column("subtitle", sa.String(300), server_default=""),
            sa.Column("image", sa.String(255)),
            sa.Column("button_text", sa.String(80), server_default=""),
            sa.Column("button_url", sa.String(300), server_default=""),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        )
        op.create_index("ix_banner_active", "banner", ["active"])
        op.create_index("ix_banner_display_order", "banner", ["display_order"])

    if "setting" not in tables:
        op.create_table(
            "setting",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(120), nullable=False),
            sa.Column("value", sa.Text(), server_default=""),
            sa.UniqueConstraint("key", name="uq_setting_key"),
        )
        op.create_index("ix_setting_key", "setting", ["key"])

    if "product" not in tables:
        op.create_table(
            "product",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("slug", sa.String(220), nullable=False),
            sa.Column("sku", sa.String(80), nullable=False),
            sa.Column("description", sa.Text(), server_default=""),
            sa.Column("price_delivery", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("price_pickup", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("stock", sa.Integer(), server_default="0", nullable=False),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=True),
            sa.Column("image", sa.String(255)),
            sa.Column("additional_images", sa.Text(), server_default=""),
            sa.Column("featured", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_product_slug"),
            sa.UniqueConstraint("sku", name="uq_product_sku"),
        )
        op.create_index("ix_product_slug", "product", ["slug"])
        op.create_index("ix_product_sku", "product", ["sku"])
        op.create_index("ix_product_category_id", "product", ["category_id"])
        op.create_index("ix_product_active", "product", ["active"])

    if "order" not in tables:
        op.create_table(
            "order",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_name", sa.String(160), nullable=False),
            sa.Column("customer_phone", sa.String(40), nullable=False),
            sa.Column("fulfillment_method", sa.String(20), nullable=False),
            sa.Column("address", sa.String(300), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("total", sa.Numeric(12, 2), nullable=False),
            sa.Column("status", sa.String(30), server_default="Nuevo", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_order_status", "order", ["status"])
        op.create_index("ix_order_created_at", "order", ["created_at"])

    if "order_item" not in tables:
        op.create_table(
            "order_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_name_snapshot", sa.String(180), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
            sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        )
        op.create_index("ix_order_item_order_id", "order_item", ["order_id"])

    if "restaurant" not in tables:
        op.create_table("restaurant",
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(180), nullable=False), sa.Column("slug", sa.String(220), nullable=False),
            sa.Column("description", sa.Text(), server_default=""), sa.Column("food_type", sa.String(120), server_default="Comida rápida"), sa.Column("logo", sa.String(255)), sa.Column("banner", sa.String(255)),
            sa.Column("address", sa.String(300), server_default=""), sa.Column("phone", sa.String(40), server_default=""), sa.Column("whatsapp", sa.String(40), server_default=""), sa.Column("instagram", sa.String(300), server_default=""), sa.Column("facebook", sa.String(300), server_default=""),
            sa.Column("meta_title", sa.String(180), server_default=""), sa.Column("meta_description", sa.String(300), server_default=""), sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False), sa.Column("accept_orders_closed", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("slug", name="uq_restaurant_slug"))
        op.create_index("ix_restaurant_slug", "restaurant", ["slug"]); op.create_index("ix_restaurant_active", "restaurant", ["active"])
    if "restaurant_user" not in tables:
        op.create_table("restaurant_user", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False), sa.Column("username", sa.String(120), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("username", name="uq_restaurant_user_username"))
        op.create_index("ix_restaurant_user_restaurant_id", "restaurant_user", ["restaurant_id"]); op.create_index("ix_restaurant_user_username", "restaurant_user", ["username"])
    if "restaurant_category" not in tables:
        op.create_table("restaurant_category", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("slug", sa.String(160), nullable=False), sa.Column("description", sa.Text(), server_default=""), sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False), sa.Column("display_order", sa.Integer(), server_default="0", nullable=False), sa.UniqueConstraint("restaurant_id", "slug", name="uq_restaurant_category_slug"))
        op.create_index("ix_restaurant_category_restaurant_id", "restaurant_category", ["restaurant_id"]); op.create_index("ix_restaurant_category_active", "restaurant_category", ["active"]); op.create_index("ix_restaurant_category_restaurant_active", "restaurant_category", ["restaurant_id", "active"])
    if "restaurant_product" not in tables:
        op.create_table("restaurant_product", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False), sa.Column("category_id", sa.Integer(), sa.ForeignKey("restaurant_category.id", ondelete="SET NULL")), sa.Column("name", sa.String(180), nullable=False), sa.Column("slug", sa.String(220), nullable=False), sa.Column("sku", sa.String(80), nullable=False), sa.Column("description", sa.Text(), server_default=""), sa.Column("price_delivery", sa.Numeric(12,2), server_default="0", nullable=False), sa.Column("price_pickup", sa.Numeric(12,2), server_default="0", nullable=False), sa.Column("stock", sa.Integer(), server_default="0", nullable=False), sa.Column("image", sa.String(255)), sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False), sa.Column("featured", sa.Boolean(), server_default=sa.false(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("restaurant_id", "slug", name="uq_restaurant_product_slug"), sa.UniqueConstraint("restaurant_id", "sku", name="uq_restaurant_product_sku"))
        op.create_index("ix_restaurant_product_restaurant_id", "restaurant_product", ["restaurant_id"]); op.create_index("ix_restaurant_product_category_id", "restaurant_product", ["category_id"]); op.create_index("ix_restaurant_product_active", "restaurant_product", ["active"])
    if "restaurant_hour" not in tables:
        op.create_table("restaurant_hour", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False), sa.Column("weekday", sa.Integer(), nullable=False), sa.Column("closed", sa.Boolean(), server_default=sa.false(), nullable=False), sa.Column("start_time", sa.String(5), server_default="19:00"), sa.Column("end_time", sa.String(5), server_default="00:00"), sa.Column("start_time_2", sa.String(5), server_default=""), sa.Column("end_time_2", sa.String(5), server_default=""), sa.UniqueConstraint("restaurant_id", "weekday", name="uq_restaurant_hour_day"))
        op.create_index("ix_restaurant_hour_restaurant_id", "restaurant_hour", ["restaurant_id"])
    if "restaurant_id" not in [c["name"] for c in inspector.get_columns("order")]:
        with op.batch_alter_table("order") as batch:
            batch.add_column(sa.Column("restaurant_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_order_restaurant_id", "restaurant", ["restaurant_id"], ["id"], ondelete="SET NULL")
        op.create_index("ix_order_restaurant_id", "order", ["restaurant_id"])
    if "restaurant_product_id" not in [c["name"] for c in inspector.get_columns("order_item")]:
        with op.batch_alter_table("order_item") as batch:
            batch.add_column(sa.Column("restaurant_product_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_order_item_restaurant_product_id", "restaurant_product", ["restaurant_product_id"], ["id"], ondelete="SET NULL")
        op.create_index("ix_order_item_restaurant_product_id", "order_item", ["restaurant_product_id"])
    if "stock_deducted" not in [c["name"] for c in inspector.get_columns("order")]:
        op.add_column("order", sa.Column("stock_deducted", sa.Boolean(), server_default=sa.false(), nullable=False))
        op.create_index("ix_order_stock_deducted", "order", ["stock_deducted"])
        # Existing confirmed orders already passed through the old stock-confirmation
        # flow, so mark them as deducted to prevent a second deduction after deploy.
        op.execute(sa.text("UPDATE \"order\" SET stock_deducted = TRUE WHERE status = 'Confirmado'"))
    if "checkout_token" not in [c["name"] for c in inspector.get_columns("order")]:
        op.add_column("order", sa.Column("checkout_token", sa.String(80), nullable=True))
        op.create_index("ix_order_checkout_token", "order", ["checkout_token"], unique=True)


def downgrade():
    # Destructive downgrade is intentionally avoided for a data-preserving production deployment.
    pass
