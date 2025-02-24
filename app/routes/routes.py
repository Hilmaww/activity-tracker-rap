from flask import Blueprint, jsonify, render_template, request, current_app
from app.models.models import Site, Ticket, TicketAction, ProblemCategory, TicketStatus, EnomAssignee
from app import db
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from sqlalchemy import or_

main_bp = Blueprint('main', __name__, template_folder='../../templates')

@main_bp.route('/')
def index():
    open_tickets = Ticket.query.filter_by(status=TicketStatus.OPEN).count()
    in_progress_tickets = Ticket.query.filter_by(status=TicketStatus.IN_PROGRESS).count()
    pending_tickets = Ticket.query.filter_by(status=TicketStatus.PENDING).count()
    resolved_tickets = Ticket.query.filter_by(status=TicketStatus.RESOLVED).count()

    return render_template('index.html', open_tickets=open_tickets,
                       in_progress_tickets=in_progress_tickets,
                       pending_tickets=pending_tickets,
                       resolved_tickets=resolved_tickets,
                       statuses=TicketStatus)

@main_bp.route('/tickets', methods=['GET'])
def list_tickets():
    # Get filter parameters
    status_filter = request.args.get('status')
    search_query = request.args.get('search')
    category_filter = request.args.get('category')
    site_filter = request.args.get('site')
    
    # Start with base query
    query = Ticket.query
    
    # Apply filters
    if status_filter:
        query = query.filter(Ticket.status == TicketStatus[status_filter])
    if category_filter:
        query = query.filter(Ticket.problem_category == ProblemCategory[category_filter])
    if site_filter:
        query = query.filter(Ticket.site_id == site_filter)
    if search_query:
        query = query.filter(or_(
            Ticket.ticket_number.ilike(f'%{search_query}%'),
            Ticket.created_by.ilike(f'%{search_query}%'),
            Ticket.description.ilike(f'%{search_query}%')
        ))
    
    tickets = query.order_by(Ticket.created_at.desc()).all()
    sites = Site.query.all()
    return render_template('tickets.html', 
                         tickets=tickets, 
                         sites=sites,
                         categories=ProblemCategory,
                         statuses=TicketStatus)

@main_bp.route('/tickets/new', methods=['GET', 'POST'])
def create_ticket():
    if request.method == 'POST':
        try:
            new_ticket = Ticket(
                ticket_number=f"TKT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                site_id=request.form['site_id'],
                problem_category=request.form['problem_category'],
                description=request.form['description'],
                created_by=request.form['created_by'],
                assigned_to_enom=request.form.get('assigned_to_enom')
            )
            db.session.add(new_ticket)
            db.session.commit()
            return render_template('create_ticket.html', tickets=Ticket.query.all(), message="Ticket created successfully", message_category="success")
        except Exception as e:
            return render_template('create_ticket.html', tickets=Ticket.query.all(), message="Ticket creation failed", message_category="danger")

    sites = Site.query.all()
    return render_template('create_ticket.html', 
                         sites=sites, 
                         categories=ProblemCategory,
                         enom_assignees=EnomAssignee)

@main_bp.route('/tickets/<int:ticket_id>/actions', methods=['POST'])
def add_action(ticket_id):
    try:
        ticket = Ticket.query.get_or_404(ticket_id)

        photo = request.files.get('photo')
        photo_path = None
        if photo:
            filename = secure_filename(photo.filename)
            # Store relative path in database
            photo_path = f'uploads/{filename}'
            # Save to external uploads directory
            full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            photo.save(full_path)

        action = TicketAction(
            ticket_id=ticket_id,
            action_text=request.form['action_text'],
            photo_path=photo_path,
            created_by=request.form['created_by']
        )

        db.session.add(action)
        db.session.commit()

        return render_template('view_ticket.html', 
                            ticket=ticket,
                            actions=TicketAction.query.filter_by(ticket_id=ticket_id).order_by(TicketAction.created_at.desc()).all(),
                            message="Action added successfully",
                            message_category="success")
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@main_bp.route('/tickets/<int:ticket_id>', methods=['GET'])
def view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    actions = TicketAction.query.filter_by(ticket_id=ticket_id).order_by(TicketAction.created_at.desc()).all()
    return render_template('view_ticket.html', ticket=ticket, actions=actions)

@main_bp.route('/tickets/<int:ticket_id>/update_status', methods=['POST'])
def update_ticket_status(ticket_id):
    try:
        ticket = Ticket.query.get_or_404(ticket_id)
        new_status = request.form.get('status')
        
        # Add an action to record the status change
        action_text = f"Status updated from {ticket.status.name} to {new_status}"
        action = TicketAction(
            ticket_id=ticket_id,
            action_text=action_text,
            created_by=request.form.get('created_by', 'system')
        )
        
        # Update the ticket status
        ticket.status = TicketStatus[new_status]
        
        # Set closed_at timestamp when status is RESOLVED
        if new_status == 'RESOLVED':
            ticket.closed_at = datetime.utcnow()
        elif ticket.closed_at is not None:
            # Clear closed_at if status is changed from RESOLVED to something else
            ticket.closed_at = None
        
        db.session.add(action)
        db.session.commit()
        
        return render_template('view_ticket.html', 
                             ticket=ticket, 
                             actions=TicketAction.query.filter_by(ticket_id=ticket_id).order_by(TicketAction.created_at.desc()).all(),
                             message="Status updated successfully",
                             message_category="success")
    except Exception as e:
        return render_template('view_ticket.html', 
                             ticket=ticket, 
                             actions=TicketAction.query.filter_by(ticket_id=ticket_id).order_by(TicketAction.created_at.desc()).all(),
                             message="Failed to update status",
                             message_category="danger")

# Add a test route
@main_bp.route('/test')
def test():
    return jsonify({"status": "ok"})
