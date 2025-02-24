"""Change EnomAssignee ATUN to JAYA

Revision ID: xxxxxxxxxxxx
Revises: previous_revision_id
Create Date: YYYY-MM-DD HH:MM:SS
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Update existing records that have ATUN to JAYA
    op.execute("UPDATE tickets SET assigned_to_enom = 'JAYA' WHERE assigned_to_enom = 'ATUN'")
    
    # Update the enum type
    op.alter_column('tickets', 'assigned_to_enom',
                    type_=sa.Enum('RIZKI', 'DOLLI', 'JAYA', 'PARLIN', name='enomassignee'),
                    existing_type=sa.Enum('RIZKI', 'DOLLI', 'ATUN', 'PARLIN', name='enomassignee'),
                    existing_nullable=True)

def downgrade():
    # Revert the enum type
    op.alter_column('tickets', 'assigned_to_enom',
                    type_=sa.Enum('RIZKI', 'DOLLI', 'ATUN', 'PARLIN', name='enomassignee'),
                    existing_type=sa.Enum('RIZKI', 'DOLLI', 'JAYA', 'PARLIN', name='enomassignee'),
                    existing_nullable=True)
    
    # Update records back to ATUN
    op.execute("UPDATE tickets SET assigned_to_enom = 'ATUN' WHERE assigned_to_enom = 'JAYA'") 