from flask import Flask, render_template, request, abort, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from urllib.parse import urlparse
from config import Config

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


def create_app(config=None):
    app = Flask(__name__)
    
    if config is None:
        app.config.from_object('config.Config')
    else:
        app.config.from_object(config)

    # Initialize Flask-Limiter with Redis
    limiter = Limiter(
        key_func=get_remote_address, 
        storage_uri="redis://localhost:6379"
    )
    limiter.init_app(app)  # This applies rate limiting to the Flask app

    # Set the SERVER_NAME to your domain
    app.config['SERVER_NAME'] = 'pataro.hilmifawwaz.xyz'

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
    
    @app.before_request
    def block_bad_user_agents():
        user_agent = request.headers.get('User-Agent', '')
        if not user_agent or 'python' in user_agent.lower() or 'curl' in user_agent.lower():
            abort(403)
    
    @app.before_request
    def detect_attackers():
        client_ip = request.remote_addr
        key = f"failed_attempts:{client_ip}"

        # Increment failed attempts (Expire after 60 sec)
        count = redis.Redis(host='localhost', port=6379, db=0).incr(key)
        redis.Redis(host='localhost', port=6379, db=0).expire(key, 60)

        if count > 10:  # More than 10 failed requests in 60 sec?
            abort(403)  # Block the user

    @app.before_request
    def validate_request():
        """Middleware to validate request parameters and URLs"""
        if request.args:
            for key, value in request.args.items():
                if isinstance(value, str):
                    # Block file:// protocol
                    if value.startswith('file:'):
                        abort(403)

                    # Validate URLs in parameters (except search queries)
                    if any(value.startswith(prefix) for prefix in ['http://', 'https://']):
                        if key == 'search':  
                            continue  # Allow URLs in search queries
                        parsed = urlparse(value)
                        if parsed.netloc not in ['cdn.jsdelivr.net', 'unpkg.com', 'code.jquery.com']:
                            abort(403)

            # Block known dangerous parameters (but only as keys, not values)
            dangerous_params = ['wp_automatic', 'action', 'preview', 'load', 'proxy']
            if any(param in request.args.keys() for param in dangerous_params):
                abort(403)

    @app.before_request
    def before_request():
        """Generate a new nonce for each request and store it in `g` (Flask's global object)."""
        if not hasattr(g, 'nonce_value'):
            g.nonce_value = Config.generate_nonce()
    
    @app.after_request
    def add_security_headers(response):
        """Dynamically add security headers, replacing the {nonce} placeholder in CSP."""
        if hasattr(g, 'nonce_value'):  # Ensure nonce_value is set
            nonce = g.nonce_value
        else:
            nonce = Config.generate_nonce()  # Fallback (shouldn't happen if before_request is working)

        if 'Content-Security-Policy' in app.config['SECURITY_HEADERS']:
            response.headers['Content-Security-Policy'] = app.config['SECURITY_HEADERS']['Content-Security-Policy'].format(nonce=nonce)
        
        for header, value in app.config['SECURITY_HEADERS'].items():
            if header != 'Content-Security-Policy':  # Avoid overriding CSP twice
                response.headers[header] = value

        return response


    @app.context_processor
    def inject_nonce():
        """Make nonce_value available in Jinja templates."""
        return {'nonce_value': getattr(g, 'nonce_value', '')}

    with app.app_context():
        db.create_all()

    return app

