import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database configuration
    SQLALCHEMY_DATABASE_URI = f'postgresql://{os.getenv("DB_USERNAME")}:{os.getenv("DB_PASSWORD")}@{os.getenv("DB_HOST")}/{os.getenv("DB_NAME")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'options': '-c timezone=UTC'
        }
    }

    # File upload configuration
    UPLOAD_FOLDER = '/var/www/uploads/enom_tracker'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Flask configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    TEMPLATES_AUTO_RELOAD = True

    # Mapbox configuration
    MAPBOX_TOKEN = os.getenv('MAPBOX_TOKEN')

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # Use in-memory SQLite for testing 