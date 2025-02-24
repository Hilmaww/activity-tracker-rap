"""update problem categories

Revision ID: update_categories
Revises: previous_revision_id
Create Date: 2024-02-24
"""
from alembic import op
import sqlalchemy as sa
from app.models.models import ProblemCategory

def upgrade():
    # Update ENVIRONMENTAL to NON-TECHNICAL
    op.execute("""
        UPDATE tickets 
        SET problem_category = 'NON-TECHNICAL' 
        WHERE problem_category = 'ENVIRONMENTAL'
    """)
    
    # Update ADMINISTRATIVE and OTHERS to NON-TECHNICAL
    op.execute("""
        UPDATE tickets 
        SET problem_category = 'NON-TECHNICAL' 
        WHERE problem_category IN ('ADMINISTRATIVE', 'OTHERS')
    """)
    
    # Drop and recreate the enum
    op.execute('DROP TYPE IF EXISTS problem_category CASCADE')
    op.execute("""
        CREATE TYPE problem_category AS ENUM ('TECHNICAL', 'NON-TECHNICAL')
    """)

def downgrade():
    # If needed, can convert back
    op.execute("""
        UPDATE tickets 
        SET problem_category = 'ENVIRONMENTAL' 
        WHERE problem_category = 'NON-TECHNICAL'
    """)