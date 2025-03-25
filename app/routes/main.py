from flask import Blueprint, render_template, request, current_app, redirect, url_for, flash, Flask, Response
from app.models import Site, Ticket, TicketAction, ProblemCategory, TicketStatus, EnomAssignee, User, DailyPlan, PlannedSite, PlanComment, PlanStatus, AlarmRecord, AlarmStatus, AlarmRemark, AlarmCategory
from app import db, logger
from datetime import datetime, timedelta
import pytz
from werkzeug.utils import secure_filename
import os
from sqlalchemy import or_, func, desc
from dotenv import load_dotenv
from flask_login import login_required, current_user
from flask import jsonify, abort
import re
import math

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

    if current_user.role == 'enom':
        username_prefix = current_user.username.split('_')[0].upper()

        status_counts = {status: 0 for status in TicketStatus}

        results = Ticket.query.filter(
            Ticket.assigned_to_enom == username_prefix # change here
        ).all()

        for ticket in results:
            status_counts[ticket.status] += 1

        open_tickets = status_counts[TicketStatus.OPEN]
        in_progress_tickets = status_counts[TicketStatus.IN_PROGRESS]
        pending_tickets = status_counts[TicketStatus.PENDING]
        resolved_tickets = status_counts[TicketStatus.RESOLVED]

    else:
        status_counts = {
            TicketStatus.OPEN: Ticket.query.filter_by(status=TicketStatus.OPEN).count(),
            TicketStatus.IN_PROGRESS: Ticket.query.filter_by(status=TicketStatus.IN_PROGRESS).count(),
            TicketStatus.PENDING: Ticket.query.filter_by(status=TicketStatus.PENDING).count(),
            TicketStatus.RESOLVED: Ticket.query.filter_by(status=TicketStatus.RESOLVED).count(),
        }
        open_tickets = status_counts[TicketStatus.OPEN]
        in_progress_tickets = status_counts[TicketStatus.IN_PROGRESS]
        pending_tickets = status_counts[TicketStatus.PENDING]
        resolved_tickets = status_counts[TicketStatus.RESOLVED]

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
        trend_labels.append(date.strftime('%d-%m-%Y'))

    # Get sites with tickets for map
    sites_with_tickets = db.session.query(
        Site,
        func.count(Ticket.id).label('ticket_count')
    ).join(
        Ticket, Site.id == Ticket.site_id
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

    # Add today's date for ENOM plan check
    today = datetime.now(jakarta_tz).date()

    # Get top 10 planned sites in the last two weeks
    two_weeks_ago = today - timedelta(days=14)
    top_planned_sites = db.session.query(
        Site.site_id,
        Site.name,
        func.count(PlannedSite.id).label('visit_count')
    ).join(
        PlannedSite,
        Site.id == PlannedSite.site_id
    ).join(
        DailyPlan,
        PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.plan_date >= two_weeks_ago,
        DailyPlan.plan_date <= today
    ).group_by(
        Site.id
    ).order_by(
        func.count(PlannedSite.id).desc()
    ).limit(10).all()

    top_planned_sites_data = {
        'site_ids': [site.site_id for site in top_planned_sites],
        'site_names': [site.name for site in top_planned_sites],
        'visit_counts': [site.visit_count for site in top_planned_sites]
    }

    # Get today's planned sites for the map
    todays_planned_sites = db.session.query(
        Site,
        DailyPlan.enom_user_id,
        User.username.label('enom_username'),
        PlannedSite.planned_actions,
        PlannedSite.estimated_duration
    ).join(
        PlannedSite,
        Site.id == PlannedSite.site_id
    ).join(
        DailyPlan,
        PlannedSite.daily_plan_id == DailyPlan.id
    ).join(
        User,
        DailyPlan.enom_user_id == User.id
    ).filter(
        DailyPlan.plan_date == today
    ).all()

    planned_site_markers = [{
        'id': site.Site.id,
        'site_id': site.Site.site_id,
        'name': site.Site.name,
        'kabupaten': site.Site.kabupaten,
        'lat': float(site.Site.lat),
        'long': float(site.Site.long),
        'enom_username': site.enom_username,
        'planned_actions': site.planned_actions,
        'estimated_duration': site.estimated_duration
    } for site in todays_planned_sites if site.Site.lat and site.Site.long]

    # Add today's plans for TSEL users
    todays_plans = None
    if current_user.is_authenticated and current_user.role == 'tsel':
        todays_plans = DailyPlan.query.filter(
            DailyPlan.plan_date == today
        ).options(
            db.joinedload(DailyPlan.enom_user),
            db.joinedload(DailyPlan.planned_sites).joinedload(PlannedSite.site)
        ).all()

    # For ENOM users, get sites that need planning
    unplanned_sites = []
    unplanned_site_ids = []
    
    if current_user.is_authenticated and current_user.role == 'enom':
        # First, get all sites with active alarms
        sites_with_active_alarms = db.session.query(
            Site,
            func.count(AlarmRecord.id).label('alarm_count'),
            func.max(AlarmRecord.priority_score).label('priority_score')
        ).join(
            AlarmRecord, Site.id == AlarmRecord.site_id
        ).filter(
            AlarmRecord.status.in_([AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED]),
            AlarmRecord.is_deleted == False
        ).group_by(Site.id).order_by(desc('priority_score')).all()
        
        # For each site, check if it's already planned
        for site, alarm_count, priority_score in sites_with_active_alarms:
            # Check if site is in any active plan
            planned = db.session.query(PlannedSite).join(
                DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
            ).filter(
                PlannedSite.site_id == site.id,
                DailyPlan.plan_date >= datetime.now().date()
            ).first()
            
            if not planned:
                site.alarm_count = alarm_count
                site.priority_score = priority_score
                unplanned_sites.append(site)
                unplanned_site_ids.append(site.id)

    # -------------------------------------------------------------
    # NEW BUSINESS DASHBOARD METRICS CALCULATION
    # -------------------------------------------------------------
    
    # 1. Site Alignment & Proactive Management
    total_sites = Site.query.count()
    # Count sites with active alarms
    sites_with_alarms_count = db.session.query(func.count(func.distinct(AlarmRecord.site_id))).filter(
        AlarmRecord.status.in_([AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED]),
        AlarmRecord.is_deleted == False
    ).scalar() or 0
    
    # Count sites that are in any active plan
    sites_in_plans_count = db.session.query(func.count(func.distinct(PlannedSite.site_id))).join(
        DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.plan_date >= datetime.now().date()
    ).scalar() or 0
    
    # Count sites with alarms but no plan
    sites_with_alarms_no_plan_count = len(unplanned_site_ids)
    
    # Calculate sites without alarms or plans
    other_sites_count = total_sites - sites_in_plans_count - sites_with_alarms_no_plan_count
    
    site_alignment = {
        'planned': sites_in_plans_count,
        'with_alarms_no_plan': sites_with_alarms_no_plan_count,
        'other': other_sites_count
    }
    
    # 2. Operational Efficiency Metrics
    # Calculate for current period (last 30 days)
    # Site Visit Efficiency = % of planned sites actually visited
    planned_sites_30_days = db.session.query(func.count(PlannedSite.id)).join(
        DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.plan_date >= current_date - timedelta(days=30),
        DailyPlan.plan_date <= current_date
    ).scalar() or 0
    
    # Estimate visited sites by checking for updated actions different from 'Not Done Yet'
    visited_sites_30_days = db.session.query(func.count(PlannedSite.id)).join(
        DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.plan_date >= current_date - timedelta(days=30),
        DailyPlan.plan_date <= current_date,
        PlannedSite.updated_actions != 'Not Done Yet'
    ).scalar() or 0
    
    visit_efficiency = round((visited_sites_30_days / planned_sites_30_days * 100) if planned_sites_30_days > 0 else 0)
    
    # Alarm Response Time = Average time to acknowledge alarms (0-100 scale where 100 is immediate response)
    # Calculate avg hours between created_at and first status change to acknowledged
    alarm_response_hours = []
    recent_alarms = AlarmRecord.query.filter(
        AlarmRecord.created_at >= thirty_days_ago,
        AlarmRecord.status != AlarmStatus.OPEN
    ).all()
    
    for alarm in recent_alarms:
        if alarm.created_at and alarm.updated_at and alarm.created_at != alarm.updated_at:
            response_time = (alarm.updated_at - alarm.created_at).total_seconds() / 3600  # hours
            alarm_response_hours.append(response_time)
    
    # Convert to a 0-100 scale where lower hours = higher score
    # Using a sigmoid function that gives ~80-90 for responses within 24 hours
    # and drops quickly for longer times
    if alarm_response_hours:
        avg_response_hours = sum(alarm_response_hours) / len(alarm_response_hours)
        response_time_score = round(100 * (1 / (1 + math.exp(0.1 * (avg_response_hours - 24)))))
    else:
        response_time_score = 50  # Default mid-point if no data
    
    # Resolution Rate = % of alarms/tickets resolved within SLA
    alarms_within_sla = 0
    total_resolved_alarms = 0
    
    resolved_alarms = AlarmRecord.query.filter(
        AlarmRecord.created_at >= thirty_days_ago,
        AlarmRecord.status == AlarmStatus.RESOLVED,
        AlarmRecord.resolved_at.isnot(None)
    ).all()
    
    for alarm in resolved_alarms:
        total_resolved_alarms += 1
        # Assume SLA is 72 hours (3 days)
        if (alarm.resolved_at - alarm.created_at).total_seconds() <= 72 * 3600:
            alarms_within_sla += 1
    
    resolution_rate = round((alarms_within_sla / total_resolved_alarms * 100) if total_resolved_alarms > 0 else 0)
    
    # Resource Utilization = Average workload distribution efficiency
    # Calculate how evenly workload is distributed among engineers
    # enom_users = User.query.filter_by(role='enom').all()
    enom_users = [u for u in User.query.filter_by(role='enom') if u.username != 'enom_user']
    workload_counts = []
    
    for user in enom_users:
        # Count user's active planned sites + assigned tickets + assigned alarms
        planned_count = db.session.query(func.count(PlannedSite.id)).join(
            DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
        ).filter(
            DailyPlan.enom_user_id == user.id,
            DailyPlan.plan_date >= current_date,
            DailyPlan.plan_date <= current_date + timedelta(days=7)
        ).scalar() or 0
        
        ticket_count = Ticket.query.filter(
            Ticket.assigned_to_id == user.id,
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.PENDING])
        ).count()
        
        # Also count by username prefix for older tickets
        username_prefix = user.username.split('_')[0].upper()
        old_ticket_count = Ticket.query.filter(
            Ticket.assigned_to_enom == username_prefix,
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.PENDING])
        ).count()
        
        total_count = planned_count + ticket_count + old_ticket_count
        workload_counts.append(total_count)
    
    # Calculate coefficient of variation - lower values mean more even distribution
    if workload_counts and len(workload_counts) > 1:
        mean_workload = sum(workload_counts) / len(workload_counts)
        variance = sum((x - mean_workload) ** 2 for x in workload_counts) / len(workload_counts)
        std_dev = math.sqrt(variance)
        cv = (std_dev / mean_workload) if mean_workload > 0 else 0
        # Convert to a 0-100 score where 100 means perfectly balanced
        resource_utilization = round(100 * (1 - min(cv, 1)))
    else:
        resource_utilization = 50  # Default mid-point
    
    # Plan Compliance = % of submitted plans that were approved
    submitted_plans = DailyPlan.query.filter(
        DailyPlan.created_at >= thirty_days_ago,
        DailyPlan.status.in_([PlanStatus.SUBMITTED, PlanStatus.APPROVED, PlanStatus.REJECTED])
    ).count()
    
    approved_plans = DailyPlan.query.filter(
        DailyPlan.created_at >= thirty_days_ago,
        DailyPlan.status == PlanStatus.APPROVED
    ).count()
    
    plan_compliance = round((approved_plans / submitted_plans * 100) if submitted_plans > 0 else 0)
    
    # Now calculate same metrics for previous period (30-60 days ago)
    previous_period_start = current_date - timedelta(days=60)
    previous_period_end = current_date - timedelta(days=30)
    
    # Site Visit Efficiency for previous period
    prev_planned_sites = db.session.query(func.count(PlannedSite.id)).join(
        DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.plan_date >= previous_period_start,
        DailyPlan.plan_date <= previous_period_end
    ).scalar() or 0
    
    # Estimate visited sites by checking for updated actions different from 'Not Done Yet'
    prev_visited_sites = db.session.query(func.count(PlannedSite.id)).join(
        DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.plan_date >= previous_period_start,
        DailyPlan.plan_date <= previous_period_end,
        PlannedSite.updated_actions != 'Not Done Yet'
    ).scalar() or 0
    
    prev_visit_efficiency = round((prev_visited_sites / prev_planned_sites * 100) if prev_planned_sites > 0 else 0)
    
    # Previous response time
    prev_alarm_response_hours = []
    prev_recent_alarms = AlarmRecord.query.filter(
        AlarmRecord.created_at >= previous_period_start,
        AlarmRecord.created_at <= previous_period_end,
        AlarmRecord.status != AlarmStatus.OPEN
    ).all()
    
    for alarm in prev_recent_alarms:
        if alarm.created_at and alarm.updated_at and alarm.created_at != alarm.updated_at:
            response_time = (alarm.updated_at - alarm.created_at).total_seconds() / 3600  # hours
            prev_alarm_response_hours.append(response_time)
    
    if prev_alarm_response_hours:
        prev_avg_response_hours = sum(prev_alarm_response_hours) / len(prev_alarm_response_hours)
        prev_response_time_score = round(100 * (1 / (1 + math.exp(0.1 * (prev_avg_response_hours - 24)))))
    else:
        prev_response_time_score = 50
    
    # Previous resolution rate
    prev_alarms_within_sla = 0
    prev_total_resolved_alarms = 0
    
    prev_resolved_alarms = AlarmRecord.query.filter(
        AlarmRecord.created_at >= previous_period_start,
        AlarmRecord.created_at <= previous_period_end,
        AlarmRecord.status == AlarmStatus.RESOLVED,
        AlarmRecord.resolved_at.isnot(None)
    ).all()
    
    for alarm in prev_resolved_alarms:
        prev_total_resolved_alarms += 1
        if (alarm.resolved_at - alarm.created_at).total_seconds() <= 72 * 3600:
            prev_alarms_within_sla += 1
    
    prev_resolution_rate = round((prev_alarms_within_sla / prev_total_resolved_alarms * 100) if prev_total_resolved_alarms > 0 else 0)
    
    # Previous resource utilization (simplified - just use a slightly lower number)
    prev_resource_utilization = max(45, resource_utilization - 5)  # Assume slight improvement
    
    # Previous plan compliance
    prev_submitted_plans = DailyPlan.query.filter(
        DailyPlan.created_at >= previous_period_start,
        DailyPlan.created_at <= previous_period_end,
        DailyPlan.status.in_([PlanStatus.SUBMITTED, PlanStatus.APPROVED, PlanStatus.REJECTED])
    ).count()
    
    prev_approved_plans = DailyPlan.query.filter(
        DailyPlan.created_at >= previous_period_start,
        DailyPlan.created_at <= previous_period_end,
        DailyPlan.status == PlanStatus.APPROVED
    ).count()
    
    prev_plan_compliance = round((prev_approved_plans / prev_submitted_plans * 100) if prev_submitted_plans > 0 else 0)
    
    # Store in dict structures for template
    operational_efficiency = {
        'visit_efficiency': visit_efficiency,
        'response_time': response_time_score,
        'resolution_rate': resolution_rate,
        'resource_utilization': resource_utilization,
        'plan_compliance': plan_compliance
    }
    
    operational_efficiency_previous = {
        'visit_efficiency': prev_visit_efficiency,
        'response_time': prev_response_time_score,
        'resolution_rate': prev_resolution_rate,
        'resource_utilization': prev_resource_utilization,
        'plan_compliance': prev_plan_compliance
    }
    
    # 3. Resource Allocation Intelligence
    # Get list of ENOM users for the chart
    enom_users_list = User.query.filter_by(role='enom').all()
    enom_usernames = [user.username for user in enom_users_list]
    
    # Calculate workload per user
    resource_allocation = {
        'planned_sites': [],
        'alarms': [],
        'tickets': []
    }
    
    for user in enom_users_list:
        # Count planned sites
        planned_sites_count = db.session.query(func.count(PlannedSite.id)).join(
            DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
        ).filter(
            DailyPlan.enom_user_id == user.id,
            DailyPlan.plan_date >= current_date,
            DailyPlan.plan_date <= current_date + timedelta(days=7)
        ).scalar() or 0
        
        resource_allocation['planned_sites'].append(planned_sites_count)
        
        # Count assigned alarms (using remarks)
        username_prefix = user.username.split('_')[0].upper()
        assigned_alarms_count = db.session.query(func.count(AlarmRemark.id)).join(
            AlarmRecord, AlarmRemark.alarm_id == AlarmRecord.id
        ).filter(
            AlarmRemark.assignee == username_prefix,
            AlarmRecord.status.in_([AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED, AlarmStatus.SCHEDULED])
        ).scalar() or 0
        
        resource_allocation['alarms'].append(assigned_alarms_count)
        
        # Count assigned tickets
        tickets_count = Ticket.query.filter(
            or_(
                Ticket.assigned_to_id == user.id,
                Ticket.assigned_to_enom == username_prefix
            ),
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.PENDING])
        ).count()
        
        resource_allocation['tickets'].append(tickets_count)
    
    # 4. Temporal Operational Performance
    # Get data for the last 7 days
    temporal_performance = {
        'plan_submissions': [],
        'alarms_resolved': [],
        'site_visits': []
    }
    
    for i in range(6, -1, -1):
        date = current_date - timedelta(days=i)
        
        # Count plan submissions
        submissions = DailyPlan.query.filter(
            DailyPlan.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(date, datetime.min.time()).astimezone(jakarta_tz),
            DailyPlan.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(date, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1)
        ).count()
        
        temporal_performance['plan_submissions'].append(submissions)
        
        # Count alarms resolved
        resolved = AlarmRecord.query.filter(
            AlarmRecord.resolved_at.isnot(None),
            AlarmRecord.resolved_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(date, datetime.min.time()).astimezone(jakarta_tz),
            AlarmRecord.resolved_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(date, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1)
        ).count()
        
        temporal_performance['alarms_resolved'].append(resolved)
        
        # Count site visits (estimated by checking for plans on that date)
        visits = db.session.query(func.count(PlannedSite.id)).join(
            DailyPlan, PlannedSite.daily_plan_id == DailyPlan.id
        ).filter(
            DailyPlan.plan_date == date,
            DailyPlan.status == PlanStatus.APPROVED
        ).scalar() or 0
        
        temporal_performance['site_visits'].append(visits)
    
    # 5. Alarm Management Scorecard
    # Calculate alarm statistics
    total_alarms = AlarmRecord.query.filter(
        AlarmRecord.is_deleted == False
    ).count()
    
    # Calculate resolution rate
    alarms_last_30_days = AlarmRecord.query.filter(
        AlarmRecord.created_at >= thirty_days_ago,
        AlarmRecord.is_deleted == False
    ).count()
    
    resolved_last_30_days = AlarmRecord.query.filter(
        AlarmRecord.created_at >= thirty_days_ago,
        AlarmRecord.status == AlarmStatus.RESOLVED,
        AlarmRecord.is_deleted == False
    ).count()
    
    alarm_resolution_rate = round((resolved_last_30_days / alarms_last_30_days * 100) if alarms_last_30_days > 0 else 0)
    
    # Calculate average resolution time
    alarm_resolution_times = []
    resolved_alarms = AlarmRecord.query.filter(
        AlarmRecord.created_at >= thirty_days_ago,
        AlarmRecord.status == AlarmStatus.RESOLVED,
        AlarmRecord.resolved_at.isnot(None),
        AlarmRecord.is_deleted == False
    ).all()
    
    for alarm in resolved_alarms:
        resolution_time = (alarm.resolved_at - alarm.created_at).total_seconds() / 3600  # hours
        alarm_resolution_times.append(resolution_time)
    
    avg_alarm_resolution_time = round(sum(alarm_resolution_times) / len(alarm_resolution_times)) if alarm_resolution_times else 0
    
    # Prepare alarm stats
    alarm_stats = {
        'total': total_alarms,
        'resolution_rate': alarm_resolution_rate,
        'avg_resolution_time': avg_alarm_resolution_time
    }
    
    # Get alarm counts by category for the last 4 weeks
    alarm_management = {
        'dates': [],
        'cell_down': [],
        'power_issues': [],
        'transport_issues': [],
        'zero_payload': [],
        'other': []
    }
    
    # Generate 4 week periods
    for i in range(4):
        week_end = current_date - timedelta(days=i*7)
        week_start = week_end - timedelta(days=6)
        week_label = f"{week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')}"
        alarm_management['dates'].append(week_label)
        
        # Count alarms by category in this week
        cell_down_count = AlarmRecord.query.filter(
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(week_start, datetime.min.time()).astimezone(jakarta_tz),
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(week_end, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1),
            AlarmRecord.category == AlarmCategory.CELL_DOWN,
            AlarmRecord.is_deleted == False
        ).count()
        
        power_issues_count = AlarmRecord.query.filter(
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(week_start, datetime.min.time()).astimezone(jakarta_tz),
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(week_end, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1),
            AlarmRecord.category == AlarmCategory.POWER_ISSUE,
            AlarmRecord.is_deleted == False
        ).count()
        
        transport_issues_count = AlarmRecord.query.filter(
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(week_start, datetime.min.time()).astimezone(jakarta_tz),
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(week_end, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1),
            AlarmRecord.category == AlarmCategory.TRANSPORT_ISSUE,
            AlarmRecord.is_deleted == False
        ).count()
        
        zero_payload_count = AlarmRecord.query.filter(
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(week_start, datetime.min.time()).astimezone(jakarta_tz),
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(week_end, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1),
            AlarmRecord.category == AlarmCategory.ZERO_PAYLOAD,
            AlarmRecord.is_deleted == False
        ).count()
        
        other_count = AlarmRecord.query.filter(
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') >= datetime.combine(week_start, datetime.min.time()).astimezone(jakarta_tz),
            AlarmRecord.created_at.op('AT TIME ZONE')('UTC').op('AT TIME ZONE')('Asia/Jakarta') < datetime.combine(week_end, datetime.max.time()).astimezone(jakarta_tz) + timedelta(seconds=1),
            AlarmRecord.category == AlarmCategory.OTHER,
            AlarmRecord.is_deleted == False
        ).count()
        
        alarm_management['cell_down'].append(cell_down_count)
        alarm_management['power_issues'].append(power_issues_count)
        alarm_management['transport_issues'].append(transport_issues_count)
        alarm_management['zero_payload'].append(zero_payload_count)
        alarm_management['other'].append(other_count)

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
                       planned_site_markers=planned_site_markers,
                       top_planned_sites_data=top_planned_sites_data,
                       mapbox_token=os.getenv('MAPBOX_TOKEN'),
                       today=today,
                       todays_plans=todays_plans,
                       unplanned_sites=unplanned_sites,
                       unplanned_site_ids=unplanned_site_ids,
                       # New business dashboard metrics
                       site_alignment=site_alignment,
                       operational_efficiency=operational_efficiency,
                       operational_efficiency_previous=operational_efficiency_previous,
                       enom_users=enom_usernames,
                       resource_allocation=resource_allocation,
                       temporal_performance=temporal_performance,
                       alarm_stats=alarm_stats,
                       alarm_management=alarm_management)

@bp.route('/tickets', methods=['GET'])
@login_required
def list_tickets():
    # Get filter parameters
    status_filter = request.args.get('status')
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category')
    
    try:
        site_filter = int(request.args.get('site')) if request.args.get('site') else None
    except ValueError:
        site_filter = None  # Gracefully handle invalid site values
    
    # Validate enums safely
    status_enum = TicketStatus[status_filter] if status_filter in TicketStatus.__members__ else None
    category_enum = ProblemCategory[category_filter] if category_filter in ProblemCategory.__members__ else None

    # Get page number, limit items per page
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 30, type=int), 100)  # Prevent abuse

    # Start with base query
    query = Ticket.query

    # Apply filters safely
    if status_enum:
        query = query.filter(Ticket.status == status_enum)
    if category_enum:
        query = query.filter(Ticket.problem_category == category_enum)
    if site_filter:
        query = query.filter(Ticket.site_id == site_filter)
    if search_query:
        query = query.filter(or_(
            Ticket.ticket_number.ilike(f"%{search_query}%"),
            Ticket.created_by.ilike(f"%{search_query}%"),
            Ticket.description.ilike(f"%{search_query}%")
        ))

    # Filter by ENOM user
    if current_user.role == 'enom':
        try:
            enom_enum = current_user.username.split('_')[0].upper()
            if enom_enum:
                query = query.filter(Ticket.assigned_to_enom == enom_enum)
        except KeyError as e:
            logger.warning(f"Invalid ENOM user: {str(e)}")

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
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)
        
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
                created_by_id=current_user.id,
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
                created_at=current_time,
                created_by_id=current_user.id
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
@login_required
def add_action(ticket_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

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
            created_by_id=current_user.id,
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
@login_required
def view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    actions = TicketAction.query.filter_by(ticket_id=ticket_id).order_by(TicketAction.created_at.desc()).all()
    return render_template('view_ticket.html', ticket=ticket, actions=actions)

@bp.route('/tickets/<int:ticket_id>/update_status', methods=['POST'])
@login_required
def update_ticket_status(ticket_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    try:
        ticket = Ticket.query.get_or_404(ticket_id)
        new_status = request.form.get('status')
        current_time = datetime.now(jakarta_tz)
        
        action_text = f"Status updated from {ticket.status.name} to {new_status}"
        action = TicketAction(
            ticket_id=ticket_id,
            action_text=action_text,
            created_by=request.form.get('created_by', 'system'),
            created_by_id=current_user.id,
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
@login_required
def edit_ticket_description(ticket_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

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

@bp.route('/api/sites/search')
@login_required
def search_sites():
    term = request.args.get('term', '')
    logger.debug(f"Search term received: {term}")
    
    try:
        # Search sites by ID or name
        query = Site.query.filter(
            or_(
                Site.site_id.ilike(f'%{term}%'),
                Site.name.ilike(f'%{term}%'),
                Site.kabupaten.ilike(f'%{term}%')
            )
        )
        
        # Debug: Print the SQL query
        logger.debug(f"SQL Query: {query}")
        
        sites = query.limit(10).all()
        logger.debug(f"Found {len(sites)} sites")
        
        results = [{
            'id': site.id,
            'text': f'{site.site_id} - {site.name}',
            'site_id': site.site_id,
            'name': site.name,
            'kabupaten': site.kabupaten
        } for site in sites]
        
        response = {
            'results': results,
            'pagination': {
                'more': False
            }
        }
        logger.debug(f"Returning response: {response}")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in site search: {str(e)}")
        return jsonify({
            'results': [],
            'pagination': {'more': False},
            'error': str(e)
        }), 500

@bp.route('/ticket/<int:ticket_id>/resolve', methods=['POST'])
@login_required
def resolve_ticket(ticket_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

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
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

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
    enom_user_filter = request.args.get('enom_user')
    
    # Base query with eager loading
    query = DailyPlan.query.options(
        db.joinedload(DailyPlan.enom_user),
        db.joinedload(DailyPlan.planned_sites).joinedload(PlannedSite.site)
    )
    
    # Rest of your code remains the same
    if current_user.role == 'enom':
        query = query.filter_by(enom_user_id=current_user.id)
    elif current_user.role != 'tsel':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.index'))
    
    if date_filter:
        query = query.filter_by(plan_date=datetime.strptime(date_filter, '%Y-%m-%d').date())
    if status_filter:
        query = query.filter_by(status=PlanStatus[status_filter])
    if enom_user_filter and current_user.role == 'tsel':
        query = query.filter_by(enom_user_id=int(enom_user_filter))
    
    # Get ENOM users for filter dropdown
    enom_users = None
    if current_user.role == 'tsel':
        enom_users = User.query.filter_by(role='enom').all()
    
    plans = query.order_by(DailyPlan.plan_date.desc()).all()
    today = datetime.now(jakarta_tz).date()
    
    return render_template('plans/list.html', 
                         plans=plans,
                         statuses=PlanStatus,
                         enom_users=enom_users,
                         today=today)

@bp.route('/plans/new', methods=['GET', 'POST'])
@login_required
def create_plan():
    if current_user.role != 'enom':
        flash('Only ENOM users can create plans', 'danger')
        return redirect(url_for('main.list_plans'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            plan_date = datetime.strptime(request.form['plan_date'], '%Y-%m-%d').date()
            if action == 'draft':

                new_plan = DailyPlan(
                    enom_user_id=current_user.id,
                    plan_date=plan_date,
                    status=PlanStatus.DRAFT
                )
                db.session.add(new_plan)
                db.session.commit()
            elif action == 'submit':
                new_plan = DailyPlan(
                    enom_user_id=current_user.id,
                    plan_date=plan_date,
                    status=PlanStatus.SUBMITTED
                )
                db.session.add(new_plan)
                db.session.commit()

            # Add planned sites
            site_ids = request.form.getlist('site_id[]')
            actions = request.form.getlist('planned_actions[]')
            visit_orders = request.form.getlist('visit_order[]')
            durations = request.form.getlist('duration[]')
            assignees = request.form.getlist('assignee[]')
            
            for i in range(len(site_ids)):
                # Get site by site_id
                site = Site.query.filter_by(site_id=site_ids[i]).first()
                if site:
                    planned_site = PlannedSite(
                        daily_plan_id=new_plan.id,
                        site_id=site.id,
                        planned_actions=actions[i],
                        visit_order=visit_orders[i],
                        estimated_duration=durations[i],
                        assignee=assignees[i]
                    )
                    db.session.add(planned_site)
            
            db.session.commit()
            flash('Plan created successfully', 'success')
            return redirect(url_for('main.view_plan', plan_id=new_plan.id))
            
        except Exception as e:
            logger.error(f"Error creating plan: {str(e)}")
            flash('Failed to create plan', 'danger')
            flash(str(e))
            return render_template('plans/create.html')
            
    return render_template('plans/create.html')

@bp.route('/plans/<int:plan_id>/submit', methods=['POST'])
@login_required
def submit_plan(plan_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    plan = DailyPlan.query.get_or_404(plan_id)
    if plan.enom_user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.list_plans'))
        
    plan.status = PlanStatus.SUBMITTED
    db.session.commit()
    
    flash('Plan submitted for review', 'success')
    return redirect(url_for('main.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>/approve', methods=['POST'])
@login_required
def approve_plan(plan_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    if current_user.role != 'tsel':
        flash('Only TSEL admin can approve plans', 'danger')
        return redirect(url_for('main.list_plans'))
        
    plan = DailyPlan.query.get_or_404(plan_id)
    plan.status = PlanStatus.APPROVED
    db.session.commit()
    
    flash('Plan approved', 'success')
    return redirect(url_for('main.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>/add_comment', methods=['POST'])
@login_required
def add_comment(plan_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    plan = DailyPlan.query.get_or_404(plan_id)
    comment_text = request.form.get('comment')
    
    if not comment_text:
        flash('Comment cannot be empty', 'danger')
        return redirect(url_for('main.view_plan', plan_id=plan_id))
    
    new_comment = PlanComment(
        daily_plan_id=plan.id,
        user_id=current_user.id,
        comment=comment_text
    )
    db.session.add(new_comment)
    db.session.commit()
    
    flash('Comment added successfully', 'success')
    return redirect(url_for('main.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>/reject', methods=['POST'])
@login_required
def reject_plan(plan_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    if current_user.role != 'tsel':
        flash('Only TSEL admin can reject plans', 'danger')
        return redirect(url_for('main.list_plans'))
        
    plan = DailyPlan.query.get_or_404(plan_id)
    reason = request.form.get('reason')
    
    if not reason:
        flash('Reason for rejection is required', 'danger')
        return redirect(url_for('main.view_plan', plan_id=plan_id))
    
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
    return redirect(url_for('main.view_plan', plan_id=plan_id))

@bp.route('/plans/<int:plan_id>', methods=['GET'])
@login_required
def view_plan(plan_id):
    # Retrieve the plan by ID
    plan = DailyPlan.query.get_or_404(plan_id)
    
    # Check if the user has permission to view the plan
    if current_user.role != 'tsel' and plan.enom_user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.list_plans'))
    
    # Retrieve planned sites and comments associated with the plan
    planned_sites = plan.planned_sites
    comments = plan.comments
    
    return render_template('plans/view.html', plan=plan, planned_sites=planned_sites, comments=comments)

@bp.route('/plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(plan_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    plan = DailyPlan.query.get_or_404(plan_id)

    # Check if the user has permission to edit the plan
    if current_user.role != 'tsel' and plan.enom_user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.list_plans'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            try:
                plan.plan_date = datetime.strptime(request.form['plan_date'], '%Y-%m-%d').date()
                new_status = PlanStatus[request.form['status']]
                
                # Clear existing planned sites
                db.session.query(PlannedSite).filter_by(daily_plan_id=plan.id).delete()

                # Add new planned sites
                site_ids = request.form.getlist('site_id[]')
                actions = request.form.getlist('planned_actions[]')
                ts = request.form.getlist('ts[]')
                durations = request.form.getlist('duration[]')
                if new_status != PlanStatus.DRAFT:
                    updated_actions = request.form.getlist('updated_actions[]')
                else:
                    updated_actions = ['Not Done Yet'] * len(site_ids)

                for i, site_id in enumerate(site_ids):
                    planned_site = PlannedSite(
                        daily_plan_id=plan.id,
                        site_id=site_id,
                        planned_actions=actions[i],
                        assignee=ts[i],
                        visit_order=i + 1,
                        estimated_duration=durations[i],
                        updated_actions=updated_actions[i] if new_status != PlanStatus.DRAFT else 'Not Done Yet'
                    )
                    db.session.add(planned_site)

                # Update status after all sites are added
                plan.status = new_status
                
                db.session.commit()
                flash('Plan updated successfully', 'success')
                return redirect(url_for('main.view_plan', plan_id=plan.id))
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating plan: {str(e)}', 'danger')
                return redirect(url_for('main.edit_plan', plan_id=plan.id))
        elif action == 'submit':
            try:
                plan.status = PlanStatus.SUBMITTED
                db.session.commit()
                flash('Plan submitted successfully', 'success')
                return redirect(url_for('main.view_plan', plan_id=plan.id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error submitting plan: {str(e)}', 'danger')
                return redirect(url_for('main.edit_plan', plan_id=plan.id))

    all_sites = Site.query.all()
    return render_template('plans/edit.html', plan=plan, sites=all_sites)

@bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_plan(plan_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)

    plan = DailyPlan.query.get_or_404(plan_id)
    
    # Check permissions
    if current_user.role != 'tsel':
        flash('You do not have permission to delete this plan. Request to delete plan from TSEL admin', 'danger')
        return redirect(url_for('main.list_plans'))
    
    try:
        db.session.delete(plan)
        db.session.commit()
        flash('Plan deleted successfully', 'success')
    except Exception as e:
        logger.error(f"Error deleting plan: {str(e)}")
        flash(f'Failed to delete plan: {str(e)}', 'danger')
    
    return redirect(url_for('main.list_plans'))

@bp.route('/api/sites/count')
@login_required
def get_sites_count():
    count = Site.query.count()
    return jsonify({'count': count})

@bp.route('/tickets/<int:ticket_id>/delete', methods=['POST'])
@login_required
def delete_ticket(ticket_id):
    if not all(is_safe_string(v) for v in request.form.values()):
        abort(400)
        
    if current_user.role != 'tsel':
        return jsonify({
            'success': False,
            'message': 'Only TSEL users can delete tickets'
        }), 403
        
    ticket = Ticket.query.get_or_404(ticket_id)
    try:
        db.session.delete(ticket)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Ticket deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@bp.after_request
def add_header(response):
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

def is_safe_string(v):
    # Check for SQL injection
    # if re.search(r'(;|--|insert|delete|update|drop|alter|create|truncate|xp_|exec|sp_|xp_cmdshell)', v, re.IGNORECASE):
    #     return False
    return True

@bp.route('/visited-sites', methods=['GET'])
@login_required
def visited_sites():
    """
    Page that displays all BTS sites that have been visited, along with visit counts.
    This serves as an overview of all site activities.
    """
    # Get filter parameters
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    time_frame = request.args.get('time_frame', 'all')
    
    # Process date range based on time frame
    today = datetime.now(jakarta_tz).date()
    
    if time_frame == '7days':
        from_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        to_date = today.strftime('%Y-%m-%d')
    elif time_frame == '30days':
        from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = today.strftime('%Y-%m-%d')
    elif time_frame == '90days':
        from_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        to_date = today.strftime('%Y-%m-%d')
    
    # Convert to date objects if provided
    from_date_obj = None
    to_date_obj = None
    
    if from_date:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    if to_date:
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Build query for visited sites
    query = db.session.query(
        Site,
        func.count(PlannedSite.id).label('visit_count')
    ).join(
        PlannedSite,
        Site.id == PlannedSite.site_id
    ).join(
        DailyPlan,
        PlannedSite.daily_plan_id == DailyPlan.id
    ).filter(
        DailyPlan.status.in_([PlanStatus.APPROVED, PlanStatus.SUBMITTED])
    )
    
    # Apply date filters if specified
    if from_date_obj:
        query = query.filter(DailyPlan.plan_date >= from_date_obj)
    if to_date_obj:
        query = query.filter(DailyPlan.plan_date <= to_date_obj)
    
    # Group by site and order by visit count (descending)
    visited_sites = query.group_by(Site.id).order_by(func.count(PlannedSite.id).desc()).all()
    
    # Get the latest visit for each site
    latest_visits = {}
    for site, _ in visited_sites:
        latest_visit_query = db.session.query(
            DailyPlan.plan_date,
            User.username
        ).join(
            PlannedSite,
            DailyPlan.id == PlannedSite.daily_plan_id
        ).join(
            User,
            DailyPlan.enom_user_id == User.id
        ).filter(
            PlannedSite.site_id == site.id,
            DailyPlan.status.in_([PlanStatus.APPROVED, PlanStatus.SUBMITTED])
        ).order_by(
            DailyPlan.plan_date.desc()
        ).first()
        
        if latest_visit_query:
            latest_visits[site.id] = {
                'date': latest_visit_query[0],
                'enom': latest_visit_query[1]
            }
    
    return render_template(
        'sites/visited_sites.html',
        visited_sites=visited_sites,
        latest_visits=latest_visits,
        time_frame=time_frame,
        from_date=from_date,
        to_date=to_date
    )

@bp.route('/site/<int:site_id>/activities', methods=['GET'])
@login_required
def site_activities(site_id):
    """
    Detailed page showing all activities performed at a specific site.
    Includes filtering options and a timeline view of actions.
    """
    # Get the site
    site = Site.query.get_or_404(site_id)
    
    # Get filter parameters
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    time_frame = request.args.get('time_frame', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of visits to show per page
    
    # Process date range based on time frame
    today = datetime.now(jakarta_tz).date()
    
    if time_frame == '7days':
        from_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        to_date = today.strftime('%Y-%m-%d')
    elif time_frame == '30days':
        from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = today.strftime('%Y-%m-%d')
    elif time_frame == '90days':
        from_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        to_date = today.strftime('%Y-%m-%d')
    
    # Convert to date objects if provided
    from_date_obj = None
    to_date_obj = None
    
    if from_date:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
    if to_date:
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
    
    # Query for all visits to this site
    query = db.session.query(
        PlannedSite,
        DailyPlan,
        User
    ).join(
        DailyPlan,
        PlannedSite.daily_plan_id == DailyPlan.id
    ).join(
        User,
        DailyPlan.enom_user_id == User.id
    ).filter(
        PlannedSite.site_id == site_id,
        DailyPlan.status.in_([PlanStatus.APPROVED, PlanStatus.SUBMITTED])
    )
    
    # Apply date filters if specified
    if from_date_obj:
        query = query.filter(DailyPlan.plan_date >= from_date_obj)
    if to_date_obj:
        query = query.filter(DailyPlan.plan_date <= to_date_obj)
    
    # Order by date (most recent first)
    query = query.order_by(DailyPlan.plan_date.desc())
    
    # Paginate the results
    paginated_visits = query.paginate(page=page, per_page=per_page)
    
    # Get ticket history for this site
    ticket_history = Ticket.query.filter(
        Ticket.site_id == site_id
    ).order_by(
        Ticket.created_at.desc()
    ).limit(5).all()
    
    return render_template(
        'sites/site_activities.html',
        site=site,
        visits=paginated_visits,
        ticket_history=ticket_history,
        time_frame=time_frame,
        from_date=from_date,
        to_date=to_date
    )
