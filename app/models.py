from app import db
from datetime import datetime
from enum import Enum
import pytz
from flask_login import UserMixin

class TicketStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class ProblemCategory(str, Enum):
    TECHNICAL = "TECHNICAL"
    NON_TECHNICAL = "NON_TECHNICAL"

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
    
    # Add relationships to tickets created and assigned
    tickets_created = db.relationship('Ticket', foreign_keys='Ticket.created_by_id', backref='creator', lazy=True)
    tickets_assigned = db.relationship('Ticket', foreign_keys='Ticket.assigned_to_id', backref='assignee', lazy=True)

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
