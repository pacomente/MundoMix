"""Add Cloudinary references to all ecommerce image-bearing models.

Revision ID: 0002_cloudinary_images
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_cloudinary_images"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {col["name"]: col for col in inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()

    product_columns = _columns(bind, "product")
    with op.batch_alter_table("product") as batch:
        if "cloudinary_public_id" not in product_columns:
            batch.add_column(sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True))
        if "additional_image_public_ids" not in product_columns:
            batch.add_column(sa.Column("additional_image_public_ids", sa.Text(), nullable=True))
        image_type = product_columns.get("image", {}).get("type")
        if getattr(image_type, "length", None) != 500:
            batch.alter_column("image", type_=sa.String(length=500), existing_type=image_type or sa.String(length=255), existing_nullable=True)

    category_columns = _columns(bind, "category")
    with op.batch_alter_table("category") as batch:
        if "cloudinary_public_id" not in category_columns:
            batch.add_column(sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True))
        image_type = category_columns.get("image", {}).get("type")
        if getattr(image_type, "length", None) != 500:
            batch.alter_column("image", type_=sa.String(length=500), existing_type=image_type or sa.String(length=255), existing_nullable=True)

    banner_columns = _columns(bind, "banner")
    with op.batch_alter_table("banner") as batch:
        if "cloudinary_public_id" not in banner_columns:
            batch.add_column(sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True))
        image_type = banner_columns.get("image", {}).get("type")
        if getattr(image_type, "length", None) != 500:
            batch.alter_column("image", type_=sa.String(length=500), existing_type=image_type or sa.String(length=255), existing_nullable=True)


def downgrade():
    # Only remove the Cloudinary columns; image URL/path columns are left intact.
    with op.batch_alter_table("banner") as batch:
        batch.drop_column("cloudinary_public_id")
    with op.batch_alter_table("category") as batch:
        batch.drop_column("cloudinary_public_id")
    with op.batch_alter_table("product") as batch:
        batch.drop_column("additional_image_public_ids")
        batch.drop_column("cloudinary_public_id")
