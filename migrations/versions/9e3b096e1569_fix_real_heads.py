"""merge final heads"""
from alembic import op
import sqlalchemy as sa

revision = '999999999999'
down_revision = ('20260918_05_schema_indexes', '20260918_04_cloudinary')
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
