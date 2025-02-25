from flask import Flask
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
    app = Flask(__name__, template_folder='../templates/')
    
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

