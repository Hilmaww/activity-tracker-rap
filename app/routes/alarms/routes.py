from flask import render_template, flash, redirect, url_for, request, jsonify, current_app, abort, session
from flask_login import login_required, current_user
from sqlalchemy import func, desc, and_
from werkzeug.utils import secure_filename
from app.routes.alarms import bp
from app import db
from app.models import Site, AlarmRecord, AlarmRemark, AlarmCategory, AlarmStatus, User
from app.utils.file_parsers import parse_alarm_file
from datetime import datetime, timedelta
import os
import uuid
import pandas as pd

# Helper functions
def allowed_file(filename):
    """Check if a file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx', 'xls', 'txt'}

def calculate_priority_score(site_id):
    """Calculate priority score based on alarm frequency and historical data."""
    # Count how many times this site appears in alarms in the last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    alarm_count = AlarmRecord.query.filter(
        AlarmRecord.site_id == site_id,
        AlarmRecord.created_at >= thirty_days_ago,
        AlarmRecord.is_deleted == False
    ).count()
    
    # Check how many times this site has been in planned_sites in the last 30 days
    from app.models import PlannedSite, DailyPlan
    plan_count = db.session.query(func.count(PlannedSite.id)).join(DailyPlan)\
                 .filter(PlannedSite.site_id == site_id,
                         DailyPlan.plan_date >= thirty_days_ago.date()).scalar()
    
    # Calculate priority score (higher = more priority)
    # Formula: (alarm_count * 2) + plan_count
    return (alarm_count * 2) + plan_count

# Routes
@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_alarm():
    """Upload alarm/program data files."""
    if current_user.role != 'tsel':
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    categories = [category.value for category in AlarmCategory]
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if not allowed_file(file.filename):
            flash('File type not allowed. Please upload CSV, Excel, or TXT files.', 'danger')
            return redirect(request.url)
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        random_prefix = uuid.uuid4().hex
        safe_filename = f"{random_prefix}_{filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(file_path)
        
        # Parse file and get preview
        category = request.form.get('category', AlarmCategory.OTHER.value)
        try:
            preview_data = parse_alarm_file(file_path, category)
            
            # Store file path in session for later processing
            if 'uploads' not in session:
                session['uploads'] = {}
            session['uploads']['alarm_file'] = {
                'path': file_path,
                'category': category
            }
            
            return render_template(
                'alarms/preview.html', 
                preview_data=preview_data, 
                filename=filename,
                category=category
            )
            
        except Exception as e:
            flash(f'Error parsing file: {str(e)}', 'danger')
            # Clean up temporary file
            if os.path.exists(file_path):
                os.remove(file_path)
            return redirect(request.url)
    
    return render_template('alarms/upload.html', categories=categories)

@bp.route('/process', methods=['POST'])
@login_required
def process_alarm():
    """Process the uploaded alarm file after preview confirmation."""
    if current_user.role != 'tsel':
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    if 'uploads' not in session or 'alarm_file' not in session['uploads']:
        flash('No file to process. Please upload a file first.', 'danger')
        return redirect(url_for('alarms.upload_alarm'))
    
    file_info = session['uploads']['alarm_file']
    file_path = file_info['path']
    category = file_info['category']
    
    if not os.path.exists(file_path):
        flash('File not found. Please upload again.', 'danger')
        return redirect(url_for('alarms.upload_alarm'))
    
    try:
        # Process file and save to database
        alarms_data = parse_alarm_file(file_path, category, preview=False)
        
        for alarm in alarms_data:
            # Find the site by site_id
            site = Site.query.filter_by(site_id=alarm['site_id']).first()
            if not site:
                continue  # Skip if site not found
            
            # Create alarm record
            new_alarm = AlarmRecord(
                site_id=site.id,
                category=category,
                description=alarm['description'],
                source_file=os.path.basename(file_path),
                uploaded_by_id=current_user.id
            )
            
            db.session.add(new_alarm)
        
        db.session.commit()
        
        # Calculate priority scores for all sites with alarms
        sites_with_alarms = db.session.query(AlarmRecord.site_id).distinct().all()
        for site_info in sites_with_alarms:
            site_id = site_info[0]
            score = calculate_priority_score(site_id)
            
            # Update all open alarms for this site
            AlarmRecord.query.filter(
                AlarmRecord.site_id == site_id,
                AlarmRecord.status == AlarmStatus.OPEN,
                AlarmRecord.is_deleted == False
            ).update({'priority_score': score})
        
        db.session.commit()
        
        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if 'uploads' in session and 'alarm_file' in session['uploads']:
            del session['uploads']['alarm_file']
        
        flash('Alarm data processed successfully.', 'success')
        return redirect(url_for('alarms.list_alarms'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing file: {str(e)}', 'danger')
        return redirect(url_for('alarms.upload_alarm'))

@bp.route('/', methods=['GET'])
@login_required
def list_alarms():
    """Display list of alarms with filtering options."""
    # Get filter parameters
    category = request.args.get('category', 'all')
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    
    # Base query
    query = AlarmRecord.query.filter(AlarmRecord.is_deleted == False)
    
    # Apply filters
    if category != 'all':
        query = query.filter(AlarmRecord.category == category)
    if status != 'all':
        query = query.filter(AlarmRecord.status == status)
    if search:
        query = query.join(Site).filter(
            Site.site_id.ilike(f'%{search}%') | 
            Site.name.ilike(f'%{search}%')
        )
    
    # Order by priority score and creation date
    alarms = query.order_by(desc(AlarmRecord.priority_score), desc(AlarmRecord.created_at)).all()
    
    # Get counts for filter badges
    category_counts = {}
    for cat in AlarmCategory:
        category_counts[cat.value] = AlarmRecord.query.filter(
            AlarmRecord.category == cat.value,
            AlarmRecord.is_deleted == False
        ).count()
    
    status_counts = {}
    for stat in AlarmStatus:
        status_counts[stat.value] = AlarmRecord.query.filter(
            AlarmRecord.status == stat.value,
            AlarmRecord.is_deleted == False
        ).count()
    
    # Get all categories and statuses for filter dropdowns
    categories = [cat.value for cat in AlarmCategory]
    statuses = [stat.value for stat in AlarmStatus]
    
    return render_template(
        'alarms/list.html',
        alarms=alarms,
        categories=categories,
        statuses=statuses,
        category_counts=category_counts,
        status_counts=status_counts,
        current_category=category,
        current_status=status,
        search=search
    )

@bp.route('/remark/<int:alarm_id>', methods=['GET', 'POST'])
@login_required
def add_remark(alarm_id):
    """Add a remark to an alarm."""
    alarm = AlarmRecord.query.get_or_404(alarm_id)
    
    if request.method == 'POST':
        try:
            planned_visit_date = datetime.strptime(
                request.form.get('planned_visit_date'), 
                '%Y-%m-%dT%H:%M'
            )
            initial_findings = request.form.get('initial_findings')
            planned_actions = request.form.get('planned_actions')
            assignee = request.form.get('assignee')
            estimated_resolution_time = request.form.get('estimated_resolution_time')
            
            # Create remark
            remark = AlarmRemark(
                alarm_id=alarm_id,
                user_id=current_user.id,
                planned_visit_date=planned_visit_date,
                initial_findings=initial_findings,
                planned_actions=planned_actions,
                assignee=assignee,
                estimated_resolution_time=estimated_resolution_time
            )
            
            db.session.add(remark)
            
            # Update alarm status
            alarm.status = AlarmStatus.SCHEDULED
            
            db.session.commit()
            
            flash('Remark added successfully.', 'success')
            return redirect(url_for('alarms.view_alarm', alarm_id=alarm_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding remark: {str(e)}', 'danger')
    
    assignees = User.query.filter(User.role == 'enom').all()
    return render_template(
        'alarms/remark.html',
        alarm=alarm,
        assignees=assignees
    )

@bp.route('/view/<int:alarm_id>', methods=['GET'])
@login_required
def view_alarm(alarm_id):
    """View alarm details including remarks."""
    alarm = AlarmRecord.query.get_or_404(alarm_id)
    remarks = AlarmRemark.query.filter(
        AlarmRemark.alarm_id == alarm_id,
        AlarmRemark.is_deleted == False
    ).order_by(desc(AlarmRemark.created_at)).all()
    
    return render_template(
        'alarms/view.html',
        alarm=alarm,
        remarks=remarks
    )

@bp.route('/resolve/<int:alarm_id>', methods=['POST'])
@login_required
def resolve_alarm(alarm_id):
    """Mark an alarm as resolved."""
    alarm = AlarmRecord.query.get_or_404(alarm_id)
    
    if current_user.role != 'tsel' and current_user.role != 'enom':
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    try:
        resolution_note = request.form.get('resolution_note', '')
        
        # Add a final remark if provided
        if resolution_note:
            remark = AlarmRemark(
                alarm_id=alarm_id,
                user_id=current_user.id,
                planned_visit_date=datetime.utcnow(),
                initial_findings='Resolved',
                planned_actions=resolution_note,
                assignee=current_user.username
            )
            db.session.add(remark)
        
        # Update alarm status
        alarm.status = AlarmStatus.RESOLVED
        alarm.resolved_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Alarm resolved successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/close/<int:alarm_id>', methods=['POST'])
@login_required
def close_alarm(alarm_id):
    """Mark an alarm as closed (requires TSEL role)."""
    if current_user.role != 'tsel':
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    alarm = AlarmRecord.query.get_or_404(alarm_id)
    
    try:
        # Update alarm status
        alarm.status = AlarmStatus.CLOSED
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Alarm closed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/delete/<int:alarm_id>', methods=['POST'])
@login_required
def delete_alarm(alarm_id):
    """Soft delete an alarm (requires TSEL role)."""
    if current_user.role != 'tsel':
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    alarm = AlarmRecord.query.get_or_404(alarm_id)
    
    try:
        # Soft delete
        alarm.is_deleted = True
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Alarm deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/stats', methods=['GET'])
@login_required
def get_alarm_stats():
    """Get alarm statistics for dashboard."""
    # Count by status
    status_counts = db.session.query(
        AlarmRecord.status, 
        func.count(AlarmRecord.id)
    ).filter(AlarmRecord.is_deleted == False).group_by(AlarmRecord.status).all()
    
    status_data = {status.value: 0 for status in AlarmStatus}
    for status, count in status_counts:
        status_data[status.value] = count
    
    # Count by category
    category_counts = db.session.query(
        AlarmRecord.category, 
        func.count(AlarmRecord.id)
    ).filter(AlarmRecord.is_deleted == False).group_by(AlarmRecord.category).all()
    
    category_data = {category.value: 0 for category in AlarmCategory}
    for category, count in category_counts:
        category_data[category.value] = count
    
    # Get top 5 sites with most alarms
    top_sites = db.session.query(
        AlarmRecord.site_id,
        func.count(AlarmRecord.id).label('count')
    ).filter(AlarmRecord.is_deleted == False).group_by(AlarmRecord.site_id)\
    .order_by(desc('count')).limit(5).all()
    
    top_sites_data = []
    for site_id, count in top_sites:
        site = Site.query.get(site_id)
        if site:
            top_sites_data.append({
                'site_id': site.site_id,
                'name': site.name,
                'count': count
            })
    
    return jsonify({
        'status_counts': status_data,
        'category_counts': category_data,
        'top_sites': top_sites_data
    })

@bp.route('/api/site-alarms/<site_id>', methods=['GET'])
@login_required
def get_site_alarms(site_id):
    """Get alarms for a specific site."""
    site = Site.query.filter_by(site_id=site_id).first_or_404()
    
    alarms = AlarmRecord.query.filter(
        AlarmRecord.site_id == site.id,
        AlarmRecord.is_deleted == False
    ).order_by(desc(AlarmRecord.created_at)).all()
    
    alarm_data = []
    for alarm in alarms:
        alarm_data.append({
            'id': alarm.id,
            'category': alarm.category,
            'description': alarm.description,
            'status': alarm.status,
            'created_at': alarm.created_at_jakarta.strftime('%Y-%m-%d %H:%M'),
            'priority_score': alarm.priority_score
        })
    
    return jsonify({
        'site': {
            'id': site.id,
            'site_id': site.site_id,
            'name': site.name,
            'location': site.kabupaten
        },
        'alarms': alarm_data
    }) 