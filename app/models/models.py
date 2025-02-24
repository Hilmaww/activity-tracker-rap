from app import db
from datetime import datetime
from enum import Enum

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

    created_by = db.Column(db.String(100), nullable=False)  # TSEL team member
    assigned_to_enom = db.Column(db.Enum(EnomAssignee), nullable=True)  # ENOM team member
    assigned_to_ts = db.Column(db.String(100))  # Technical Support member

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = db.Column(db.DateTime)

    # Relationships
    actions = db.relationship('TicketAction', backref='ticket', lazy=True)

class TicketAction(db.Model):
    __tablename__ = 'ticket_actions'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    action_text = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(255))  # Path to stored photo
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
