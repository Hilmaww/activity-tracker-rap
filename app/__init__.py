from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

db = SQLAlchemy()

def create_app():
    app = Flask(__name__, template_folder='../templates/')
    
    # Configuration
    username = os.getenv('DB_USERNAME')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{username}:{password}@{host}/{db_name}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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

    return app

