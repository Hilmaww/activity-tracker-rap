"""Add Telegram bot integration support

Revision ID: add_telegram_integration
Revises: your_previous_revision_id
Create Date: 2024-06-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_telegram_integration'
down_revision = 'your_previous_revision_id'  # Replace with your actual previous revision ID
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add Telegram fields to users table
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('telegram_username', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('telegram_full_name', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('telegram_registered_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('is_telegram_active', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('users', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')))
    
    # Create unique constraint and index for telegram_id
    op.create_unique_constraint('uq_users_telegram_id', 'users', ['telegram_id'])
    op.create_index('idx_users_telegram_id', 'users', ['telegram_id'])

    # 2. Add Telegram fields to tickets table
    op.add_column('tickets', sa.Column('telegram_created', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('tickets', sa.Column('telegram_notifications_sent', sa.Boolean(), nullable=True, server_default='false'))
    op.create_index('idx_tickets_telegram_created', 'tickets', ['telegram_created'])

    # 3. Add Telegram fields to ticket_actions table
    op.add_column('ticket_actions', sa.Column('telegram_created', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('ticket_actions', sa.Column('telegram_message_id', sa.BigInteger(), nullable=True))
    op.create_index('idx_ticket_actions_telegram_message_id', 'ticket_actions', ['telegram_message_id'])

    # 4. Add Telegram fields to daily_plans table
    op.add_column('daily_plans', sa.Column('telegram_created', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('daily_plans', sa.Column('telegram_message_id', sa.BigInteger(), nullable=True))
    op.add_column('daily_plans', sa.Column('area_name', sa.String(length=200), nullable=True))
    op.add_column('daily_plans', sa.Column('total_sites_planned', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('daily_plans', sa.Column('sites_completed', sa.Integer(), nullable=True, server_default='0'))
    
    op.create_index('idx_daily_plans_telegram_created', 'daily_plans', ['telegram_created'])
    op.create_index('idx_daily_plans_plan_date', 'daily_plans', ['plan_date'])
    op.create_index('idx_daily_plans_user_date', 'daily_plans', ['enom_user_id', 'plan_date'])

    # 5. Add Telegram fields to planned_sites table
    op.add_column('planned_sites', sa.Column('telegram_updated', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('planned_sites', sa.Column('telegram_update_message_id', sa.BigInteger(), nullable=True))
    op.add_column('planned_sites', sa.Column('completed_at', sa.DateTime(), nullable=True))
    op.add_column('planned_sites', sa.Column('is_completed', sa.Boolean(), nullable=True, server_default='false'))
    
    op.create_index('idx_planned_sites_is_completed', 'planned_sites', ['is_completed'])
    op.create_index('idx_planned_sites_plan_completed', 'planned_sites', ['daily_plan_id', 'is_completed'])

    # 6. Add Telegram fields to plan_comments table
    op.add_column('plan_comments', sa.Column('telegram_created', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('plan_comments', sa.Column('telegram_message_id', sa.BigInteger(), nullable=True))

    # 7. Add Telegram fields to alarm_records table
    op.add_column('alarm_records', sa.Column('telegram_broadcasted', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('alarm_records', sa.Column('last_broadcast_at', sa.DateTime(), nullable=True))
    op.add_column('alarm_records', sa.Column('broadcast_count', sa.Integer(), nullable=True, server_default='0'))
    
    op.create_index('idx_alarm_records_telegram_broadcasted', 'alarm_records', ['telegram_broadcasted'])
    op.create_index('idx_alarm_records_last_broadcast_at', 'alarm_records', ['last_broadcast_at'])
    op.create_index('idx_alarm_records_site_status', 'alarm_records', ['site_id', 'status'], 
                   postgresql_where=sa.text('is_deleted = false'))

    # 8. Add Telegram fields to alarm_remarks table
    op.add_column('alarm_remarks', sa.Column('telegram_created', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('alarm_remarks', sa.Column('telegram_message_id', sa.BigInteger(), nullable=True))

    # 9. Create telegram_sessions table
    op.create_table('telegram_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('current_state', sa.String(length=50), nullable=True, server_default='idle'),
        sa.Column('session_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for telegram_sessions
    op.create_index('idx_telegram_sessions_telegram_user_id', 'telegram_sessions', ['telegram_user_id'])
    op.create_index('idx_telegram_sessions_user_id', 'telegram_sessions', ['user_id'])
    op.create_index('idx_telegram_sessions_chat_id', 'telegram_sessions', ['chat_id'])
    op.create_index('idx_telegram_sessions_expires_at', 'telegram_sessions', ['expires_at'])
    op.create_index('idx_telegram_sessions_user_state', 'telegram_sessions', ['user_id', 'current_state'])

    # 10. Create telegram_broadcasts table
    op.create_table('telegram_broadcasts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('broadcast_type', sa.String(length=50), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=True),
        sa.Column('content_summary', sa.Text(), nullable=True),
        sa.Column('alarms_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('recipients_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('sent_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_successful', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for telegram_broadcasts
    op.create_index('idx_telegram_broadcasts_chat_id', 'telegram_broadcasts', ['chat_id'])
    op.create_index('idx_telegram_broadcasts_sent_at', 'telegram_broadcasts', ['sent_at'])
    op.create_index('idx_telegram_broadcasts_type', 'telegram_broadcasts', ['broadcast_type'])

    # 11. Create trigger function and triggers for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    # Apply triggers
    op.execute("""
        DROP TRIGGER IF EXISTS update_users_updated_at ON users;
        CREATE TRIGGER update_users_updated_at 
            BEFORE UPDATE ON users 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        DROP TRIGGER IF EXISTS update_telegram_sessions_updated_at ON telegram_sessions;
        CREATE TRIGGER update_telegram_sessions_updated_at 
            BEFORE UPDATE ON telegram_sessions 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # 12. Add data integrity constraints
    op.create_check_constraint('chk_users_telegram_id_positive', 'users', 
                              sa.text('telegram_id IS NULL OR telegram_id > 0'))
    
    op.create_check_constraint('chk_alarm_records_broadcast_count_non_negative', 'alarm_records', 
                              sa.text('broadcast_count >= 0'))
    
    op.create_check_constraint('chk_daily_plans_sites_completed_valid', 'daily_plans', 
                              sa.text('sites_completed >= 0 AND sites_completed <= total_sites_planned'))
    
    op.create_check_constraint('chk_daily_plans_total_sites_non_negative', 'daily_plans', 
                              sa.text('total_sites_planned >= 0'))
    
    op.create_check_constraint('chk_telegram_broadcasts_counts_non_negative', 'telegram_broadcasts', 
                              sa.text('alarms_count >= 0 AND recipients_count >= 0'))

    # 13. Create view for active Telegram users
    op.execute("""
        CREATE OR REPLACE VIEW active_telegram_users AS
        SELECT 
            u.id,
            u.username,
            u.role,
            u.telegram_id,
            u.telegram_username,
            u.telegram_full_name,
            u.telegram_registered_at,
            u.is_telegram_active
        FROM users u
        WHERE u.telegram_id IS NOT NULL 
          AND u.is_telegram_active = TRUE;
    """)


def downgrade():
    # Drop view
    op.execute("DROP VIEW IF EXISTS active_telegram_users;")
    
    # Drop triggers and function
    op.execute("DROP TRIGGER IF EXISTS update_telegram_sessions_updated_at ON telegram_sessions;")
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON users;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    
    # Drop constraints
    op.drop_constraint('chk_telegram_broadcasts_counts_non_negative', 'telegram_broadcasts')
    op.drop_constraint('chk_daily_plans_total_sites_non_negative', 'daily_plans')
    op.drop_constraint('chk_daily_plans_sites_completed_valid', 'daily_plans')
    op.drop_constraint('chk_alarm_records_broadcast_count_non_negative', 'alarm_records')
    op.drop_constraint('chk_users_telegram_id_positive', 'users')
    
    # Drop tables (indexes will be dropped automatically)
    op.drop_table('telegram_broadcasts')
    op.drop_table('telegram_sessions')
    
    # Drop indexes and columns from existing tables
    op.drop_index('idx_alarm_records_site_status', 'alarm_records')
    op.drop_index('idx_alarm_records_last_broadcast_at', 'alarm_records')
    op.drop_index('idx_alarm_records_telegram_broadcasted', 'alarm_records')
    op.drop_column('alarm_records', 'broadcast_count')
    op.drop_column('alarm_records', 'last_broadcast_at')
    op.drop_column('alarm_records', 'telegram_broadcasted')
    
    op.drop_column('alarm_remarks', 'telegram_message_id')
    op.drop_column('alarm_remarks', 'telegram_created')
    
    op.drop_column('plan_comments', 'telegram_message_id')
    op.drop_column('plan_comments', 'telegram_created')
    
    op.drop_index('idx_planned_sites_plan_completed', 'planned_sites')
    op.drop_index('idx_planned_sites_is_completed', 'planned_sites')
    op.drop_column('planned_sites', 'is_completed')
    op.drop_column('planned_sites', 'completed_at')
    op.drop_column('planned_sites', 'telegram_update_message_id')
    op.drop_column('planned_sites', 'telegram_updated')
    
    op.drop_index('idx_daily_plans_user_date', 'daily_plans')
    op.drop_index('idx_daily_plans_plan_date', 'daily_plans')
    op.drop_index('idx_daily_plans_telegram_created', 'daily_plans')
    op.drop_column('daily_plans', 'sites_completed')
    op.drop_column('daily_plans', 'total_sites_planned')
    op.drop_column('daily_plans', 'area_name')
    op.drop_column('daily_plans', 'telegram_message_id')
    op.drop_column('daily_plans', 'telegram_created')
    
    op.drop_index('idx_ticket_actions_telegram_message_id', 'ticket_actions')
    op.drop_column('ticket_actions', 'telegram_message_id')
    op.drop_column('ticket_actions', 'telegram_created')
    
    op.drop_index('idx_tickets_telegram_created', 'tickets')
    op.drop_column('tickets', 'telegram_notifications_sent')
    op.drop_column('tickets', 'telegram_created')
    
    op.drop_index('idx_users_telegram_id', 'users')
    op.drop_constraint('uq_users_telegram_id', 'users')
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'is_telegram_active')
    op.drop_column('users', 'telegram_registered_at')
    op.drop_column('users', 'telegram_full_name')
    op.drop_column('users', 'telegram_username')
    op.drop_column('users', 'telegram_id')