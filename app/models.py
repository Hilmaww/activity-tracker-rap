from app import db
from datetime import datetime
from enum import Enum
import pytz
from flask_login import UserMixin
from werkzeug.security import generate_password_hash
import re

class TicketStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class ProblemCategory(str, Enum):
    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"
    SUPPORT = "SUPPORT"

class EnomAssignee(str, Enum):
    RIZKI = "RIZKI"
    DOLLI = "DOLLI"
    THARDIZON = "THARDIZON"
    MUJAHID = "MUJAHID"

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'tsel' or 'enom'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    password_changed_at = db.Column(db.DateTime)
    
    # NEW: Telegram integration fields
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=True)  # Telegram user ID
    telegram_username = db.Column(db.String(100), nullable=True)  # Telegram @username
    telegram_full_name = db.Column(db.String(200), nullable=True)  # Telegram display name
    telegram_registered_at = db.Column(db.DateTime, nullable=True)  # When telegram was linked
    is_telegram_active = db.Column(db.Boolean, default=True)  # Whether to receive telegram notifications
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Add relationships to tickets created and assigned
    tickets_created = db.relationship('Ticket', foreign_keys='Ticket.created_by_id', backref='creator', lazy=True)
    tickets_assigned = db.relationship('Ticket', foreign_keys='Ticket.assigned_to_id', backref='assignee', lazy=True)

    def set_password(self, password):
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", password):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", password):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise ValueError("Password must contain at least one special character")
            
        self.password_hash = generate_password_hash(password)

class Site(db.Model):
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    tower_owner = db.Column(db.String(100), nullable=False)
    long = db.Column(db.Float, nullable=False)
    lat = db.Column(db.Float, nullable=False)
    kabupaten = db.Column(db.String(100), nullable=False)

    # Relationships
    tickets = db.relationship('Ticket', backref='site', lazy=True)

class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(50), unique=True, nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    problem_category = db.Column(db.Enum(ProblemCategory), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(TicketStatus), default=TicketStatus.OPEN)

    # Keep the existing fields for backward compatibility
    created_by = db.Column(db.String(100), nullable=False)  # TSEL team member
    assigned_to_enom = db.Column(db.Enum(EnomAssignee), nullable=True)  # ENOM team member
    assigned_to_ts = db.Column(db.String(100))  # Technical Support member
    
    # Add new fields for user relationships
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)  # New field for resolved timestamp
    closed_at = db.Column(db.DateTime)

    # NEW: Telegram integration fields
    telegram_created = db.Column(db.Boolean, default=False)  # Whether created via telegram
    telegram_notifications_sent = db.Column(db.Boolean, default=False)  # Track notifications

    # Relationships
    actions = db.relationship('TicketAction', backref='ticket', lazy=True, cascade='all, delete-orphan')

    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        if self.created_at:
            return self.created_at.astimezone(jakarta_tz)
        return None

    @property
    def closed_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        if self.closed_at:
            return self.closed_at.astimezone(jakarta_tz)
        return None
        
    @property
    def resolved_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        if self.resolved_at:
            return self.resolved_at.astimezone(jakarta_tz)
        return None

class TicketAction(db.Model):
    __tablename__ = 'ticket_actions'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    action_text = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(255))  # Path to stored photo
    
    # Keep existing field for backward compatibility
    created_by = db.Column(db.String(100), nullable=False)
    
    # Add new field for user relationship
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', foreign_keys=[created_by_id])
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # NEW: Telegram integration fields
    telegram_created = db.Column(db.Boolean, default=False)  # Whether created via telegram
    telegram_message_id = db.Column(db.BigInteger, nullable=True)  # Original telegram message ID

    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        if self.created_at:
            return self.created_at.astimezone(jakarta_tz)
        return None

class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class DailyPlan(db.Model):
    __tablename__ = 'daily_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    enom_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum(PlanStatus), default=PlanStatus.DRAFT)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # NEW: Telegram integration fields
    telegram_created = db.Column(db.Boolean, default=False)  # Whether created via telegram
    telegram_message_id = db.Column(db.BigInteger, nullable=True)  # Original telegram message ID
    area_name = db.Column(db.String(200), nullable=True)  # Area name from plan text
    total_sites_planned = db.Column(db.Integer, default=0)  # Total sites in plan
    sites_completed = db.Column(db.Integer, default=0)  # Sites marked as completed
    
    # Relationships
    planned_sites = db.relationship('PlannedSite', backref='daily_plan', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('PlanComment', backref='daily_plan', lazy=True, cascade='all, delete-orphan')
    enom_user = db.relationship('User', backref='daily_plans', lazy=True)

    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.created_at.astimezone(jakarta_tz) if self.created_at else None

    @property
    def completion_percentage(self):
        """Calculate completion percentage"""
        if self.total_sites_planned == 0:
            return 0.0
        return (self.sites_completed / self.total_sites_planned) * 100

class PlannedSite(db.Model):
    __tablename__ = 'planned_sites'

    id = db.Column(db.Integer, primary_key=True)
    daily_plan_id = db.Column(db.Integer, db.ForeignKey('daily_plans.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    planned_actions = db.Column(db.Text, nullable=False)
    visit_order = db.Column(db.Integer, nullable=False)
    estimated_duration = db.Column(db.Integer, default=60)  # in minutes
    assignee = db.Column(db.String(100))  # Assignee from plan text
    updated_actions = db.Column(db.Text, default='Not Done Yet')  # Updated actions status

    # NEW: Telegram integration fields
    telegram_updated = db.Column(db.Boolean, default=False)  # Whether updated via telegram
    telegram_update_message_id = db.Column(db.BigInteger, nullable=True)  # Update message ID
    completed_at = db.Column(db.DateTime, nullable=True)  # When marked as completed
    is_completed = db.Column(db.Boolean, default=False)  # Completion status
    is_deleted = db.Column(db.Boolean, default=False) # Soft delete flag

    site = db.relationship('Site', backref='planned_sites', lazy=True)

    @property
    def completed_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.completed_at.astimezone(jakarta_tz) if self.completed_at else None

    @property
    def site_id_str(self):
        """Get the site_id string from the related Site object."""
        return self.site.site_id if self.site else "N/A"


class PlanComment(db.Model):
    __tablename__ = 'plan_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    daily_plan_id = db.Column(db.Integer, db.ForeignKey('daily_plans.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # NEW: Telegram integration fields
    telegram_created = db.Column(db.Boolean, default=False)  # Whether created via telegram
    telegram_message_id = db.Column(db.BigInteger, nullable=True)  # Original telegram message ID

    user = db.relationship('User', backref='plan_comment', lazy=True)

    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.created_at.astimezone(jakarta_tz) if self.created_at else None

# Alarm management models (existing with minor additions)
class AlarmCategory(str, Enum):
    CELL_DOWN = "CELL_DOWN"
    ZERO_PAYLOAD = "ZERO_PAYLOAD"
    POWER_ISSUE = "POWER_ISSUE"
    TRANSPORT_ISSUE = "TRANSPORT_ISSUE"
    OTHER = "OTHER"

class AlarmStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SCHEDULED = "SCHEDULED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class AlarmRecord(db.Model):
    __tablename__ = 'alarm_records'

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    category = db.Column(db.Enum(AlarmCategory), nullable=False)
    description = db.Column(db.Text, nullable=False)
    source_file = db.Column(db.String(255))
    status = db.Column(db.Enum(AlarmStatus), default=AlarmStatus.OPEN)
    priority_score = db.Column(db.Integer, default=0)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    is_deleted = db.Column(db.Boolean, default=False)  # For soft delete

    # NEW: Telegram integration fields
    telegram_broadcasted = db.Column(db.Boolean, default=False)  # Whether included in broadcast
    last_broadcast_at = db.Column(db.DateTime, nullable=True)  # Last broadcast time
    broadcast_count = db.Column(db.Integer, default=0)  # Number of times broadcasted

    # Relationships
    site = db.relationship('Site', backref='alarms', lazy=True)
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id], backref='uploaded_alarms', lazy=True)
    remarks = db.relationship('AlarmRemark', backref='alarm', lazy=True, cascade='all, delete-orphan')
    
    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.created_at.astimezone(jakarta_tz) if self.created_at else None
    
    @property
    def resolved_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.resolved_at.astimezone(jakarta_tz) if self.resolved_at else None

class AlarmRemark(db.Model):
    __tablename__ = 'alarm_remarks'
    
    id = db.Column(db.Integer, primary_key=True)
    alarm_id = db.Column(db.Integer, db.ForeignKey('alarm_records.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    planned_visit_date = db.Column(db.DateTime, nullable=False)
    initial_findings = db.Column(db.Text, nullable=False)
    planned_actions = db.Column(db.Text, nullable=False)
    assignee = db.Column(db.String(100))
    estimated_resolution_time = db.Column(db.Integer)  # in minutes
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)  # For soft delete
    
    # NEW: Telegram integration fields
    telegram_created = db.Column(db.Boolean, default=False)  # Whether created via telegram
    telegram_message_id = db.Column(db.BigInteger, nullable=True)  # Original telegram message ID
    
    # Relationships
    user = db.relationship('User', backref='alarm_remarks', lazy=True)
    
    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.created_at.astimezone(jakarta_tz) if self.created_at else None
    
    @property
    def planned_visit_date_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.planned_visit_date.astimezone(jakarta_tz) if self.planned_visit_date else None

# NEW: Telegram Bot specific models
class TelegramSession(db.Model):
    """Track user sessions and conversation states in Telegram"""
    __tablename__ = 'telegram_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    telegram_user_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    chat_id = db.Column(db.BigInteger, nullable=False)
    
    current_state = db.Column(db.String(50), default='idle')  # idle, awaiting_plan, awaiting_update, etc.
    session_data = db.Column(db.JSON, nullable=True)  # Store temporary session data
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)  # Session expiration
    
    user = db.relationship('User', backref='telegram_sessions', lazy=True)
    
    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.created_at.astimezone(jakarta_tz) if self.created_at else None

class TelegramBroadcast(db.Model):
    """Track telegram broadcasts for audit and analytics"""
    __tablename__ = 'telegram_broadcasts'
    
    id = db.Column(db.Integer, primary_key=True)
    broadcast_type = db.Column(db.String(50), nullable=False)  # 'alarm', 'test', 'announcement'
    chat_id = db.Column(db.BigInteger, nullable=False)
    message_id = db.Column(db.BigInteger, nullable=True)  # Telegram message ID
    
    content_summary = db.Column(db.Text, nullable=True)  # Brief summary of broadcast content
    alarms_count = db.Column(db.Integer, default=0)  # Number of alarms in broadcast
    recipients_count = db.Column(db.Integer, default=0)  # Number of recipients
    
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_successful = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text, nullable=True)  # Error details if failed
    
    @property
    def sent_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.sent_at.astimezone(jakarta_tz) if self.sent_at else None