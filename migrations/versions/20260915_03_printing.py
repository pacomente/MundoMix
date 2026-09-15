"""Gastronomía 3.0: professional order printing and per-restaurant print settings."""
from alembic import op
import sqlalchemy as sa

revision = "20260915_03_printing"
down_revision = "20260915_01_restaurants"
branch_labels = None
depends_on = None

def _cols(table):
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()

def upgrade():
    if "printed_at" not in _cols("order"):
        op.add_column("order", sa.Column("printed_at", sa.DateTime(), nullable=True))
    if "print_settings" not in _cols("restaurant"):
        op.add_column("restaurant", sa.Column("print_settings", sa.JSON(), nullable=True))
    op.execute("UPDATE restaurant SET print_settings = '{}' WHERE print_settings IS NULL")
    op.alter_column("restaurant", "print_settings", nullable=False)

def downgrade():
    # Non-destructive by policy: production data is never removed by downgrade.
    pass
