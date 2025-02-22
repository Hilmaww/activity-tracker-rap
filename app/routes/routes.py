from flask import Blueprint, jsonify, render_template, request
from app.models.models import Site, Ticket, TicketAction, ProblemCategory
from app import db
from datetime import datetime
from werkzeug.utils import secure_filename
import os

main_bp = Blueprint('main', __name__, template_folder='../../templates')

@main_bp.route('/')
def index():
    return render_template('index.html', tickets=Ticket.query.all())

@main_bp.route('/tickets', methods=['GET'])
def list_tickets():
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template('tickets.html', tickets=tickets)

@main_bp.route('/tickets/new', methods=['GET', 'POST'])
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
            return render_template('create_ticket.html', tickets=Ticket.query.all(), message="Ticket created successfully", message_category="success")
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    sites = Site.query.all()
    return render_template('create_ticket.html', sites=sites, categories=ProblemCategory)

@main_bp.route('/tickets/<int:ticket_id>/actions', methods=['POST'])
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

# Add a test route
@main_bp.route('/test')
def test():
    return jsonify({"status": "ok"})
