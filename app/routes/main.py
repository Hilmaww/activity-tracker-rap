from flask import Blueprint, render_template, request, current_app, redirect, url_for, flash
from app.models import Site, Ticket, TicketAction, ProblemCategory, TicketStatus, EnomAssignee, User, DailyPlan, PlannedSite, PlanComment, PlanStatus
from app import db, logger
from datetime import datetime, timedelta
import pytz
from werkzeug.utils import secure_filename
import os
from sqlalchemy import or_, func
from dotenv import load_dotenv
from flask_login import login_required, current_user

bp = Blueprint('main', __name__, template_folder='../../templates')

load_dotenv()  # Add this near the top of the file

# Get Jakarta timezone
jakarta_tz = pytz.timezone('Asia/Jakarta')

@bp.route('/')
def index():
    # Check if user is authenticated first
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
        
    # Then proceed with all your existing code
    # Get current date and 30 days ago date in Jakarta time
    current_datetime = datetime.now(jakarta_tz)
    current_date = current_datetime.date()
    
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
    
    for i in range(6, -1, -1):
        date = current_date - timedelta(days=i)
        
        # Create start and end timestamps for Jakarta date
        start_of_day = datetime.combine(date, datetime.min.time()).astimezone(jakarta_tz)
        end_of_day = datetime.combine(date, datetime.max.time()).astimezone(jakarta_tz)
        
        # Query using AT TIME ZONE to convert timestamps to Jakarta time before comparison
        tickets = Ticket.query.filter(
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= start_of_day,
            Ticket.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < end_of_day + timedelta(seconds=1)
        ).all()
        
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
        'ticket_count': site.ticket_count,
        'status_counts': {
            'OPEN': Ticket.query.filter(
                Ticket.site_id == site.Site.id,
                Ticket.status == TicketStatus.OPEN
            ).count(),
            'IN_PROGRESS': Ticket.query.filter(
                Ticket.site_id == site.Site.id,
                Ticket.status == TicketStatus.IN_PROGRESS
            ).count(),
            'PENDING': Ticket.query.filter(
                Ticket.site_id == site.Site.id,
                Ticket.status == TicketStatus.PENDING
            ).count()
        },
        'status': max(
            ['OPEN', 'IN_PROGRESS', 'PENDING'],
            key=lambda s: Ticket.query.filter(
                Ticket.site_id == site.Site.id,
                Ticket.status == getattr(TicketStatus, s)
            ).count()
        ) if site.ticket_count > 0 else 'NONE'
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
                       site_markers=site_markers,
                       mapbox_token=os.getenv('MAPBOX_TOKEN'))

@bp.route('/tickets', methods=['GET'])
@login_required
def list_tickets():
    # Get filter parameters
    status_filter = request.args.get('status')
    search_query = request.args.get('search')
    category_filter = request.args.get('category')
    site_filter = request.args.get('site')
    
    # Get page number from request args, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    
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

@bp.route('/tickets/new', methods=['GET', 'POST'])
@login_required
def create_ticket():
    if current_user.role != 'tsel':
        flash('Only Tsel users can create tickets')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            current_time = datetime.now(jakarta_tz)
            
            new_ticket = Ticket(
                ticket_number=f"TKT-{current_time.strftime('%Y%m%d%H%M%S')}",
                site_id=request.form['site_id'],
                problem_category=request.form['problem_category'],
                description=request.form['description'],
                created_by=current_user.username,
                assigned_to_enom=request.form.get('assigned_to_enom'),
                created_at=current_time,
                status=TicketStatus.OPEN
            )
            db.session.add(new_ticket)
            db.session.commit()
            
            # Add initial ticket action for creation
            action = TicketAction(
                ticket_id=new_ticket.id,
                action_text="Ticket created",
                created_by=current_user.username,
                created_at=current_time
            )
            db.session.add(action)
            db.session.commit()
            
            flash('Ticket created successfully', 'success')
            return redirect(url_for('main.list_tickets'))
        except Exception as e:
            logger.error(f"Error creating ticket: {str(e)}")
            flash("Ticket creation failed", "danger")
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

@bp.route('/tickets/<int:ticket_id>/actions', methods=['POST'])
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

@bp.route('/tickets/<int:ticket_id>', methods=['GET'])
def view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    actions = TicketAction.query.filter_by(ticket_id=ticket_id).order_by(TicketAction.created_at.desc()).all()
    return render_template('view_ticket.html', ticket=ticket, actions=actions)

@bp.route('/tickets/<int:ticket_id>/update_status', methods=['POST'])
@login_required
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
            ticket.resolved_at = current_time
        elif new_status == 'CLOSED':
            ticket.closed_at = current_time
        elif ticket.resolved_at is not None:
            ticket.resolved_at = None
        
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

@bp.route('/ticket/<int:ticket_id>/edit-description', methods=['POST'])
def edit_ticket_description(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    description = request.form.get('description')
    if description is not None:
        ticket.description = description
        ticket.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Ticket description updated successfully!', 'success')
    else:
        flash('No description provided!', 'error')
    
    return redirect(url_for('main.view_ticket', ticket_id=ticket_id))

@bp.route('/test')
def test():
    return jsonify({"status": "ok"})

@bp.route('/api/sites/search', methods=['GET'])
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

@bp.route('/ticket/<int:ticket_id>/resolve', methods=['POST'])
@login_required
def resolve_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if current_user.role != 'enom' or ticket.assigned_to_id != current_user.id:
        flash('Only assigned ENOM users can resolve tickets')
        return redirect(url_for('main.view_ticket', ticket_id=ticket_id))
    
    ticket.status = 'resolved'
    ticket.resolved_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('main.view_ticket', ticket_id=ticket_id))

@bp.route('/ticket/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if current_user.role != 'tsel':
        flash('Only Tsel users can close tickets')
        return redirect(url_for('main.view_ticket', ticket_id=ticket_id))
    
    if ticket.status != 'resolved':
        flash('Ticket must be resolved before closing')
        return redirect(url_for('main.view_ticket', ticket_id=ticket_id))
    
    ticket.status = 'closed'
    ticket.closed_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('main.view_ticket', ticket_id=ticket_id))

@bp.route('/plans', methods=['GET'])
@login_required
def list_plans():
    # Get filter parameters
    date_filter = request.args.get('date')
    status_filter = request.args.get('status')
    
    query = DailyPlan.query
    
    # Apply filters based on role
    if current_user.role == 'enom':
        query = query.filter_by(enom_user_id=current_user.id)
    elif current_user.role != 'tsel_admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.index'))
    
    if date_filter:
        query = query.filter_by(plan_date=datetime.strptime(date_filter, '%Y-%m-%d').date())
    if status_filter:
        query = query.filter_by(status=PlanStatus[status_filter])
    
    plans = query.order_by(DailyPlan.plan_date.desc()).all()
    return render_template('plans/list.html', plans=plans, statuses=PlanStatus)

@bp.route('/plans/new', methods=['GET', 'POST'])
@login_required
def create_plan():
    if current_user.role != 'enom':
        flash('Only ENOM users can create plans', 'danger')
        return redirect(url_for('plans.list_plans'))
        
    if request.method == 'POST':
        try:
            plan_date = datetime.strptime(request.form['plan_date'], '%Y-%m-%d').date()
            
            # Check if plan already exists for this date
            existing_plan = DailyPlan.query.filter_by(
                enom_user_id=current_user.id,
                plan_date=plan_date
            ).first()
            
            if existing_plan:
                flash('A plan already exists for this date', 'warning')
                return redirect(url_for('plans.edit_plan', plan_id=existing_plan.id))
            
            new_plan = DailyPlan(
                enom_user_id=current_user.id,
                plan_date=plan_date,
                status=PlanStatus.DRAFT
            )
            db.session.add(new_plan)
            db.session.commit()
            
            # Add planned sites
            site_ids = request.form.getlist('site_id[]')
            actions = request.form.getlist('planned_actions[]')
            durations = request.form.getlist('duration[]')
            
            for i, site_id in enumerate(site_ids):
                planned_site = PlannedSite(
                    daily_plan_id=new_plan.id,
                    site_id=site_id,
                    planned_actions=actions[i],
                    visit_order=i+1,
                    estimated_duration=durations[i]
                )
                db.session.add(planned_site)
            
            db.session.commit()
            flash('Plan created successfully', 'success')
            return redirect(url_for('plans.view_plan', plan_id=new_plan.id))
            
        except Exception as e:
            logger.error(f"Error creating plan: {str(e)}")
            flash('Failed to create plan', 'danger')
            return render_template('plans/create.html', sites=Site.query.all())

@bp.route('/plans/<int:plan_id>/submit', methods=['POST'])
@login_required
def submit_plan(plan_id):
    plan = DailyPlan.query.get_or_404(plan_id)
    if plan.enom_user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('plans.list_plans'))
        
    plan.status = PlanStatus.SUBMITTED
    db.session.commit()
    
    flash('Plan submitted for review', 'success')
    return redirect(url_for('plans.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>/approve', methods=['POST'])
@login_required
def approve_plan(plan_id):
    if current_user.role != 'tsel_admin':
        flash('Only TSEL admin can approve plans', 'danger')
        return redirect(url_for('plans.list_plans'))
        
    plan = DailyPlan.query.get_or_404(plan_id)
    plan.status = PlanStatus.APPROVED
    db.session.commit()
    
    flash('Plan approved', 'success')
    return redirect(url_for('plans.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>/add_comment', methods=['POST'])
@login_required
def add_comment(plan_id):
    plan = DailyPlan.query.get_or_404(plan_id)
    comment_text = request.form.get('comment')
    
    if not comment_text:
        flash('Comment cannot be empty', 'danger')
        return redirect(url_for('plans.view_plan', plan_id=plan_id))
    
    new_comment = PlanComment(
        daily_plan_id=plan.id,
        user_id=current_user.id,
        comment=comment_text
    )
    db.session.add(new_comment)
    db.session.commit()
    
    flash('Comment added successfully', 'success')
    return redirect(url_for('plans.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>/reject', methods=['POST'])
@login_required
def reject_plan(plan_id):
    if current_user.role != 'tsel_admin':
        flash('Only TSEL admin can reject plans', 'danger')
        return redirect(url_for('plans.list_plans'))
        
    plan = DailyPlan.query.get_or_404(plan_id)
    reason = request.form.get('reason')
    
    if not reason:
        flash('Reason for rejection is required', 'danger')
        return redirect(url_for('plans.view_plan', plan_id=plan_id))
    
    plan.status = PlanStatus.REJECTED
    db.session.commit()
    
    # Optionally, you can add a comment for the rejection
    comment = PlanComment(
        daily_plan_id=plan.id,
        user_id=current_user.id,
        comment=f'Rejected: {reason}'
    )
    db.session.add(comment)
    db.session.commit()
    
    flash('Plan rejected', 'success')
    return redirect(url_for('plans.view_plan', plan_id=plan_id))
