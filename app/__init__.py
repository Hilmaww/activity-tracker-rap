from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Initialize extensions outside of create_app
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# Setup logging
logger = logging.getLogger('enom_tracker')
logger.setLevel(logging.INFO)

# Create handlers
handler = logging.handlers.SysLogHandler(address='/dev/log')
formatter = logging.Formatter('%(name)s[%(process)d]: %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Also log to a file for easier debugging
file_handler = logging.FileHandler('/var/log/enom_tracker/app.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

load_dotenv()

def create_app(config=None):
    app = Flask(__name__)
    
    # Configure app
    if config is None:
        app.config.from_object('config.Config')
    else:
        app.config.from_object(config)

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Setup logging
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Register blueprints
    from app.routes.main import bp as main_bp
    from app.routes.auth import bp as auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

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

    # Import models and create tables
    from app.models import User  # Move this import here
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    # Make sure log directory exists
    os.makedirs('/var/log/enom_tracker', exist_ok=True)

    return app

