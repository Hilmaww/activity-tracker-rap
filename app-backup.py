from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from enum import Enum
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import os
from werkzeug.utils import secure_filename

db = SQLAlchemy()

class TicketStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class ProblemCategory(str, Enum):
    TECHNICAL = "TECHNICAL"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    OTHERS = "OTHERS"

class Site(db.Model):
    __tablename__ = 'sites'
    
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
    assigned_to_enom = db.Column(db.String(100))  # ENOM team member
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

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:muridhilmi27@localhost/tel_reporting'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tickets', methods=['GET'])
def list_tickets():
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template('tickets.html', tickets=tickets)

@app.route('/tickets/new', methods=['GET', 'POST'])
def create_ticket():
    if request.method == 'POST':
        try:
            new_ticket = Ticket(
                ticket_number=f"TKT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                site_id=request.form['site_id'],
                problem_category=request.form['problem_category'],
                description=request.form['description'],
                created_by=request.form['created_by']
            )
            db.session.add(new_ticket)
            db.session.commit()
            return jsonify({'message': 'Ticket created successfully', 'ticket_id': new_ticket.id})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
            
    sites = Site.query.all()
    return render_template('create_ticket.html', sites=sites, categories=ProblemCategory)

@app.route('/tickets/<int:ticket_id>/actions', methods=['POST'])
def add_action(ticket_id):
    try:
        ticket = Ticket.query.get_or_404(ticket_id)
        
        photo = request.files.get('photo')
        photo_path = None
        if photo:
            filename = secure_filename(photo.filename)
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(photo_path)
        
        action = TicketAction(
            ticket_id=ticket_id,
            action_text=request.form['action_text'],
            photo_path=photo_path,
            created_by=request.form['created_by']
        )
        
        db.session.add(action)
        db.session.commit()
        
        return jsonify({'message': 'Action added successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
