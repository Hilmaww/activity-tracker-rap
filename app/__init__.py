from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import logging
from logging.handlers import RotatingFileHandler

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

db = SQLAlchemy()

def create_app():
    app = Flask(__name__, template_folder='../templates/')
    
    migrate = Migrate(app, db)

    # Setup logging
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Configuration
    username = os.getenv('DB_USERNAME')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{username}:{password}@{host}/{db_name}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = '/var/www/uploads/enom_tracker'
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'options': '-c timezone=UTC'
        }
    }

    # Initialize extensions
    db.init_app(app)

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Register blueprints
    from app.routes.routes import main_bp
    app.register_blueprint(main_bp)

    # Create tables
    with app.app_context():
        db.create_all()

    # Make sure log directory exists
    os.makedirs('/var/log/enom_tracker', exist_ok=True)

    return app

