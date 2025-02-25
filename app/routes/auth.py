from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User
from app import db, limiter
import re
from datetime import datetime, timedelta

bp = Blueprint('auth', __name__, url_prefix='/auth')

def is_safe_url(target):
    ref_url = request.host_url
    test_url = target.replace(ref_url, '')
    return not bool(re.search(r'[^/\w\s-]', test_url))

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please provide both username and password.', 'danger')
            return redirect(url_for('auth.login'))
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Check if account is locked
        if user.login_attempts >= 5 and user.last_failed_login:
            lockout_time = user.last_failed_login + timedelta(minutes=15)
            if datetime.utcnow() < lockout_time:
                flash('Account is temporarily locked. Please try again later.', 'danger')
                return redirect(url_for('auth.login'))
            else:
                # Reset login attempts after lockout period
                user.login_attempts = 0
                user.last_failed_login = None
                db.session.commit()
        
        # Successful login
        login_user(user)
        user.login_attempts = 0
        user.last_failed_login = None
        db.session.commit()
        
        # Redirect to requested page if safe
        next_page = request.args.get('next')
        if not next_page or not is_safe_url(next_page):
            next_page = url_for('main.index')
        
        return redirect(next_page)
    
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    # Clear session
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login')) 