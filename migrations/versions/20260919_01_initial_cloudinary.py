"""Initial MundoMix schema plus Cloudinary references and stock safety."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260919_01"
down_revision = None
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {column["name"] for column in inspect(bind).get_columns(table)} if inspect(bind).has_table(table) else set()


def _add_if_missing(bind, table, column, type_, **kwargs):
    if column not in _columns(bind, table):
        op.add_column(table, sa.Column(column, type_, **kwargs))


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("category"):
        op.create_table(
            "category",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False, unique=True),
            sa.Column("slug", sa.String(length=140), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("image", sa.String(length=1000), nullable=True),
            sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    else:
        _add_if_missing(bind, "category", "cloudinary_public_id", sa.String(255), nullable=True)
        _add_if_missing(bind, "category", "image", sa.String(1000), nullable=True)
        if bind.dialect.name == "postgresql":
            op.alter_column("category", "image", type_=sa.String(1000), existing_type=sa.String(255), existing_nullable=True)

    if not insp.has_table("admin"):
        op.create_table(
            "admin",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=120), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
        )

    if not insp.has_table("banner"):
        op.create_table(
            "banner",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=180), nullable=True),
            sa.Column("subtitle", sa.String(length=300), nullable=True),
            sa.Column("image", sa.String(length=1000), nullable=True),
            sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True),
            sa.Column("button_text", sa.String(length=80), nullable=True),
            sa.Column("button_url", sa.String(length=300), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        )
    else:
        _add_if_missing(bind, "banner", "cloudinary_public_id", sa.String(255), nullable=True)
        _add_if_missing(bind, "banner", "image", sa.String(1000), nullable=True)
        if bind.dialect.name == "postgresql":
            op.alter_column("banner", "image", type_=sa.String(1000), existing_type=sa.String(255), existing_nullable=True)

    if not insp.has_table("setting"):
        op.create_table(
            "setting",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(length=80), nullable=False, unique=True),
            sa.Column("value", sa.Text(), nullable=True),
        )

    if not insp.has_table("product"):
        op.create_table(
            "product",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("slug", sa.String(length=220), nullable=False, unique=True),
            sa.Column("sku", sa.String(length=80), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("price_delivery", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("price_pickup", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=True),
            sa.Column("image", sa.String(length=1000), nullable=True),
            sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True),
            sa.Column("additional_images", sa.Text(), nullable=True),
            sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_product_slug", "product", ["slug"], unique=True)
        op.create_index("ix_product_sku", "product", ["sku"], unique=True)
        op.create_index("ix_product_category_id", "product", ["category_id"], unique=False)
    else:
        _add_if_missing(bind, "product", "cloudinary_public_id", sa.String(255), nullable=True)
        _add_if_missing(bind, "product", "image", sa.String(1000), nullable=True)
        _add_if_missing(bind, "product", "additional_images", sa.Text(), nullable=True)
        # Existing short image columns are widened when the dialect supports it.
        if bind.dialect.name == "postgresql":
            op.alter_column("product", "image", type_=sa.String(1000), existing_type=sa.String(255), existing_nullable=True)

    if not insp.has_table("order"):
        op.create_table(
            "order",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_name", sa.String(length=160), nullable=False),
            sa.Column("customer_phone", sa.String(length=40), nullable=False),
            sa.Column("fulfillment_method", sa.String(length=20), nullable=False),
            sa.Column("address", sa.String(length=300), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("total", sa.Numeric(12, 2), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="Nuevo"),
            sa.Column("stock_deducted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_order_status", "order", ["status"])
        op.create_index("ix_order_created_at", "order", ["created_at"])
    else:
        _add_if_missing(bind, "order", "stock_deducted", sa.Boolean(), nullable=False, server_default=sa.false())
        # Orders that were already confirmed before this audit had their stock
        # deducted by the previous admin flow. Mark them so a later reconfirmation
        # cannot deduct the same stock twice.
        bind.execute(text("UPDATE \"order\" SET stock_deducted = TRUE WHERE status IN ('Confirmado','Preparando','Listo','En camino','Entregado') AND stock_deducted = FALSE"))

    if not insp.has_table("order_item"):
        op.create_table(
            "order_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("product_name_snapshot", sa.String(length=180), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
            sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        )
        op.create_index("ix_order_item_order_id", "order_item", ["order_id"])


def downgrade():
    # The initial migration is deliberately conservative for existing databases.
    # Removing tables/columns in production must be an explicit reviewed change.
    pass
