"""Convert datetime to WIB timezone

Revision ID: xxxxxxxxxxxx
Revises: previous_revision_id
Create Date: YYYY-MM-DD HH:MM:SS
"""
from alembic import op
import sqlalchemy as sa
from datetime import timedelta

def upgrade():
    # Add 7 hours to all existing datetime values to convert from UTC to WIB
    connection = op.get_bind()
    
    # Update tickets table
    connection.execute("""
        UPDATE tickets 
        SET created_at = created_at + INTERVAL '7 hours',
            updated_at = updated_at + INTERVAL '7 hours',
            closed_at = closed_at + INTERVAL '7 hours'
        WHERE closed_at IS NOT NULL
    """)
    
    # Update ticket_actions table
    connection.execute("""
        UPDATE ticket_actions 
        SET created_at = created_at + INTERVAL '7 hours'
    """)

def downgrade():
    # Subtract 7 hours to convert back to UTC
    connection = op.get_bind()
    
    # Update tickets table
    connection.execute("""
        UPDATE tickets 
        SET created_at = created_at - INTERVAL '7 hours',
            updated_at = updated_at - INTERVAL '7 hours',
            closed_at = closed_at - INTERVAL '7 hours'
        WHERE closed_at IS NOT NULL
    """)
    
    # Update ticket_actions table
    connection.execute("""
        UPDATE ticket_actions 
        SET created_at = created_at - INTERVAL '7 hours'
    """) 