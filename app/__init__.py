from flask import Flask, render_template, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from urllib.parse import urlparse

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

# Setup logging with sensitive data masking
class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        sensitive_fields = ['password', 'token', 'secret', 'key']
        for field in sensitive_fields:
            if hasattr(record, 'msg') and field in str(record.msg).lower():
                record.msg = str(record.msg).replace(getattr(record, field), '***')
        return True

logger = logging.getLogger('enom_tracker')
logger.setLevel(logging.INFO)
logger.addFilter(SensitiveDataFilter())

# Create handlers with secure permissions
if not os.path.exists('/var/log/enom_tracker'):
    os.makedirs('/var/log/enom_tracker', mode=0o750)

handler = logging.handlers.SysLogHandler(address='/dev/log')
file_handler = logging.FileHandler('/var/log/enom_tracker/app.log', mode='a')
formatter = logging.Formatter('%(name)s[%(process)d]: %(levelname)s - %(message)s')
handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(file_handler)

load_dotenv()

def validate_request():
    """Middleware to validate request parameters and URLs"""
    if request.args:
        # Block file:// protocol
        for value in request.args.values():
            if isinstance(value, str):
                if value.startswith('file:'):
                    abort(403)
                
                # Validate URLs in parameters
                if any(value.startswith(prefix) for prefix in ['http://', 'https://']):
                    parsed = urlparse(value)
                    # Only allow specific domains
                    if parsed.netloc not in ['cdn.jsdelivr.net', 'unpkg.com', 'code.jquery.com']:
                        abort(403)
        
        # Block known dangerous parameters
        dangerous_params = ['wp_automatic', 'action', 'preview', 'load', 'proxy']
        if any(param in request.args for param in dangerous_params):
            abort(403)

def create_app(config=None):
    app = Flask(__name__)
    
    if config is None:
        app.config.from_object('config.Config')
    else:
        app.config.from_object(config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    # Ensure upload directory exists with secure permissions
    os.makedirs(app.config['UPLOAD_FOLDER'], mode=0o750, exist_ok=True)

    # Add security headers
    @app.after_request
    def add_security_headers(response):
        for header, value in app.config['SECURITY_HEADERS'].items():
            response.headers[header] = value
        return response

    # Register blueprints
    from app.routes.main import bp as main_bp
    from app.routes.auth import bp as auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    # Error handlers
    @app.errorhandler(401)
    def unauthorized(error):
        logger.error(f"401 error: {str(error)}")
        return render_template('errors/401.html'), 401
    
    @app.errorhandler(404)
    def page_not_found(error):
        logger.error(f"404 error: {str(error)}")
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(error):
        logger.error(f"500 error: {str(error)}")
        return render_template('errors/500.html'), 500

    # Import models
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.before_request
    def log_request_info():
        app.logger.debug('Headers: %s', request.headers)
        app.logger.debug('Body: %s', request.get_data())

    app.before_request(validate_request)

    with app.app_context():
        db.create_all()

    return app

