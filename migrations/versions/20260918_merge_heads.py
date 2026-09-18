"""merge multiple heads"""
from alembic import op
import sqlalchemy as sa

revision = "20260918_merge_heads"
down_revision = ("20260915_01_restaurants", "20260915_03_printing")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
