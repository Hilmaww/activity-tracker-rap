"""update problem categories

Revision ID: update_categories
Revises: previous_revision_id
Create Date: 2024-02-24
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Update ADMINISTRATIVE and OTHERS to NON TECHNICAL
    op.execute("""
        UPDATE tickets 
        SET problem_category = 'NON TECHNICAL' 
        WHERE problem_category IN ('ADMINISTRATIVE', 'OTHERS')
    """)

def downgrade():
    pass 