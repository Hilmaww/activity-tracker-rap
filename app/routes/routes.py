from flask import Blueprint, jsonify, render_template, request, current_app, redirect, url_for
from app.models.models import Site, Ticket, TicketAction, ProblemCategory, TicketStatus, EnomAssignee
from app import db, logger
from datetime import datetime, timedelta
import pytz
from werkzeug.utils import secure_filename
import os
from sqlalchemy import or_, func

main_bp = Blueprint('main', __name__, template_folder='../../templates')

# Get Jakarta timezone
jakarta_tz = pytz.timezone('Asia/Jakarta')

@main_bp.route('/')
def index():
    # Get current date and 30 days ago date in Jakarta time
    current_datetime = datetime.now(jakarta_tz)
    current_date = current_datetime.date()
    current_app.logger.info(f"Current Jakarta datetime: {current_datetime}")
    current_app.logger.info(f"Current Jakarta date: {current_date}")
    
    # Current status counts (existing)
    open_tickets = Ticket.query.filter_by(status=TicketStatus.OPEN).count()
    in_progress_tickets = Ticket.query.filter_by(status=TicketStatus.IN_PROGRESS).count()
    pending_tickets = Ticket.query.filter_by(status=TicketStatus.PENDING).count()
    resolved_tickets = Ticket.query.filter_by(status=TicketStatus.RESOLVED).count()

    # Total tickets in last 30 days (using timezone aware query)
    total_30_days = Ticket.query.filter(
        Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= 
        datetime.combine(current_date - timedelta(days=30), datetime.min.time()).astimezone(jakarta_tz)
    ).count()

    # Status distribution for last 30 days
    thirty_days_ago = datetime.combine(current_date - timedelta(days=30), datetime.min.time()).astimezone(jakarta_tz)
    status_30_days = {
        'OPEN': Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
            Ticket.status == TicketStatus.OPEN
        ).count(),
        'IN_PROGRESS': Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
            Ticket.status == TicketStatus.IN_PROGRESS
        ).count(),
        'PENDING': Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
            Ticket.status == TicketStatus.PENDING
        ).count(),
        'RESOLVED': Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
            Ticket.status == TicketStatus.RESOLVED
        ).count()
    }

    # Problem category distribution for last 30 days
    category_distribution = {}
    for category in ProblemCategory:
        count = Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
            Ticket.problem_category == category
        ).count()
        category_distribution[category.name] = count

    # Average resolution time in the last 30 days
    resolved_tickets_30_days = Ticket.query.filter(
        Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
        Ticket.closed_at.isnot(None)
    ).all()
    
    resolution_times = []
    for ticket in resolved_tickets_30_days:
        # Convert timestamps to Jakarta time
        created_at_jkt = ticket.created_at.astimezone(jakarta_tz)
        closed_at_jkt = ticket.closed_at.astimezone(jakarta_tz)
        resolution_time = closed_at_jkt - created_at_jkt
        resolution_times.append(resolution_time.total_seconds() / 3600)  # Convert to hours
    
    avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

    # Get assignee distribution for last 30 days
    assignee_distribution = {}
    for assignee in EnomAssignee:
        count = Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago,
            Ticket.assigned_to_enom == assignee
        ).count()
        assignee_distribution[assignee.name] = count

    # Get top 5 sites with most tickets in last 30 days
    top_sites = db.session.query(
        Site.site_id,
        Site.name,
        func.count(Ticket.id).label('ticket_count')
    ).join(
        Ticket,
        Site.id == Ticket.site_id
    ).filter(
        Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= thirty_days_ago
    ).group_by(
        Site.id
    ).order_by(
        func.count(Ticket.id).desc()
    ).limit(5).all()

    top_sites_data = {
        'site_ids': [site.site_id for site in top_sites],
        'site_names': [site.name for site in top_sites],
        'ticket_counts': [site.ticket_count for site in top_sites]
    }

    # Get trend data for the last 7 days
    trend_data = []
    trend_labels = []
    
    current_app.logger.info("\nDebug 7-day trend data:")
    for i in range(6, -1, -1):
        date = current_date - timedelta(days=i)
        
        # Create start and end timestamps for Jakarta date
        start_of_day = datetime.combine(date, datetime.min.time()).astimezone(jakarta_tz)
        end_of_day = datetime.combine(date, datetime.max.time()).astimezone(jakarta_tz)
        
        current_app.logger.info(f"\nDate bucket: {date}")
        current_app.logger.info(f"Start of day: {start_of_day}")
        current_app.logger.info(f"End of day: {end_of_day}")
        
        # Query using AT TIME ZONE to convert timestamps to Jakarta time before comparison
        tickets = Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= start_of_day,
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < end_of_day + timedelta(seconds=1)
        ).all()
        
        current_app.logger.info(f"Tickets found for {date}:")
        for ticket in tickets:
            jakarta_time = ticket.created_at.astimezone(jakarta_tz)
            current_app.logger.info(f"- Ticket {ticket.ticket_number}: created_at = {ticket.created_at} (UTC) = {jakarta_time} (Jakarta)")
        
        count = len(tickets)
        trend_data.append(count)
        trend_labels.append(date.strftime('%Y-%m-%d'))

    # Get sites with active tickets and their coordinates
    sites_with_tickets = db.session.query(
        Site,
        func.count(Ticket.id).label('ticket_count')
    ).join(
        Ticket,
        Site.id == Ticket.site_id
    ).filter(
        Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.PENDING])
    ).group_by(Site.id).all()

    # Format site data for the map
    site_markers = [{
        'id': site.Site.id,
        'site_id': site.Site.site_id,
        'name': site.Site.name,
        'kabupaten': site.Site.kabupaten,
        'lat': float(site.Site.lat),
        'long': float(site.Site.long),
        'ticket_count': site.ticket_count
    } for site in sites_with_tickets if site.Site.lat and site.Site.long]

    return render_template('index.html',
                       open_tickets=open_tickets,
                       in_progress_tickets=in_progress_tickets,
                       pending_tickets=pending_tickets,
                       resolved_tickets=resolved_tickets,
                       total_30_days=total_30_days,
                       status_30_days=status_30_days,
                       assignee_distribution=assignee_distribution,
                       top_sites_data=top_sites_data,
                       category_distribution=category_distribution,
                       avg_resolution_time=round(avg_resolution_time, 1),
                       trend_data=trend_data,
                       trend_labels=trend_labels,
                       statuses=TicketStatus,
                       site_markers=site_markers)

@main_bp.route('/tickets', methods=['GET'])
def list_tickets():
    # Get filter parameters
    status_filter = request.args.get('status')
    search_query = request.args.get('search')
    category_filter = request.args.get('category')
    site_filter = request.args.get('site')
    
    # Get page number from request args, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 30  # Number of items per page
    
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
    
    # Order and paginate the query
    pagination = query.order_by(Ticket.created_at.desc()).paginate(
        page=page, 
        per_page=per_page,
        error_out=False
    )
    
    sites = Site.query.all()
    return render_template('tickets.html', 
                         pagination=pagination,
                         tickets=pagination.items, 
                         sites=sites,
                         categories=ProblemCategory,
                         statuses=TicketStatus)

@main_bp.route('/tickets/new', methods=['GET', 'POST'])
def create_ticket():
    if request.method == 'POST':
        try:
            # Make sure we're using timezone-aware datetime
            current_time = datetime.now(jakarta_tz)
            
            new_ticket = Ticket(
                ticket_number=f"TKT-{current_time.strftime('%Y%m%d%H%M%S')}",
                site_id=request.form['site_id'],
                problem_category=request.form['problem_category'],
                description=request.form['description'],
                created_by=request.form['created_by'],
                assigned_to_enom=request.form.get('assigned_to_enom'),
                created_at=current_time  # This will now be timezone-aware
            )
            db.session.add(new_ticket)
            db.session.commit()
            
            # Redirect to the tickets list instead of rendering template
            return redirect(url_for('main.list_tickets'))
        except Exception as e:
            return render_template('create_ticket.html', 
                                sites=Site.query.all(), 
                                categories=ProblemCategory,
                                enom_assignees=EnomAssignee,
                                message="Ticket creation failed", 
                                message_category="danger")

    sites = Site.query.all()
    return render_template('create_ticket.html', 
                         sites=sites, 
                         categories=ProblemCategory,
                         enom_assignees=EnomAssignee)

@main_bp.route('/tickets/<int:ticket_id>/actions', methods=['POST'])
def add_action(ticket_id):
    try:
        ticket = Ticket.query.get_or_404(ticket_id)
        current_time = datetime.now(jakarta_tz)

        photo = request.files.get('photo')
        photo_path = None
        if photo:
            filename = secure_filename(photo.filename)
            photo_path = f'uploads/{filename}'
            full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            photo.save(full_path)

        action = TicketAction(
            ticket_id=ticket_id,
            action_text=request.form['action_text'],
            photo_path=photo_path,
            created_by=request.form['created_by'],
            created_at=current_time
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
        current_time = datetime.now(jakarta_tz)
        
        action_text = f"Status updated from {ticket.status.name} to {new_status}"
        action = TicketAction(
            ticket_id=ticket_id,
            action_text=action_text,
            created_by=request.form.get('created_by', 'system'),
            created_at=current_time
        )
        
        ticket.status = TicketStatus[new_status]
        
        if new_status == 'RESOLVED':
            ticket.closed_at = current_time
        elif ticket.closed_at is not None:
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

@main_bp.route('/api/sites/search', methods=['GET'])
def search_sites():
    search_term = request.args.get('term', '')
    
    # Query sites with search term
    sites = Site.query.filter(
        or_(
            Site.name.ilike(f'%{search_term}%'),
            Site.site_id.ilike(f'%{search_term}%'),
            Site.kabupaten.ilike(f'%{search_term}%')
        )
    ).limit(50).all()  # Limit results for performance
    
    # Format results for Select2
    results = [{
        'id': site.id,
        'text': f'{site.site_id} - {site.name}',  # This is what Select2 uses for display
        'site_id': site.site_id,
        'name': site.name,
        'kabupaten': site.kabupaten
    } for site in sites]
    
    return jsonify({
        'results': results,
        'pagination': {
            'more': False
        }
    })
