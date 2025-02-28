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
    JAYA = "JAYA"
    PARLIN = "PARLIN"

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

    # Relationships
    actions = db.relationship('TicketAction', backref='ticket', lazy=True)

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
    
    # Relationships
    planned_sites = db.relationship('PlannedSite', backref='daily_plan', lazy=True)
    comments = db.relationship('PlanComment', backref='daily_plan', lazy=True)
    enom_user = db.relationship('User', backref='daily_plans', lazy=True)

    @property
    def created_at_jakarta(self):
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        return self.created_at.astimezone(jakarta_tz) if self.created_at else None

class PlannedSite(db.Model):
    __tablename__ = 'planned_sites'
    
    id = db.Column(db.Integer, primary_key=True)
    daily_plan_id = db.Column(db.Integer, db.ForeignKey('daily_plans.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    planned_actions = db.Column(db.Text, nullable=False)
    visit_order = db.Column(db.Integer, nullable=False)
    estimated_duration = db.Column(db.Integer)  # in minutes

    site =  db.relationship('Site', backref='planned_sites', lazy=True)
    daily_plan = db.relationship('DailyPlan', backref='planned_sites', lazy=True)
    
class PlanComment(db.Model):
    __tablename__ = 'plan_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    daily_plan_id = db.Column(db.Integer, db.ForeignKey('daily_plans.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
