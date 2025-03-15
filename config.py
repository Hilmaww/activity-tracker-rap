import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Validate required environment variables
    required_env_vars = [
        'DB_USERNAME', 'DB_PASSWORD', 'DB_HOST', 'DB_NAME', 
        'FLASK_SECRET_KEY', 'MAPBOX_TOKEN'
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Database configuration with connection pooling
    SQLALCHEMY_DATABASE_URI = f'postgresql://{os.getenv("DB_USERNAME")}:{os.getenv("DB_PASSWORD")}@{os.getenv("DB_HOST")}/{os.getenv("DB_NAME")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'connect_args': {
            'options': '-c timezone=UTC',
            'sslmode': 'require'  # Require SSL for database connections
        }
    }

    # File upload security
    UPLOAD_FOLDER = '/var/www/uploads/enom_tracker'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # Flask security configuration
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY')
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.getenv('FLASK_SECRET_KEY')
    
    # Security Headers
    SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",  # Enforce HTTPS
    "X-Content-Type-Options": "nosniff",  # Prevent MIME-type sniffing
    "X-Frame-Options": "DENY",  # Prevent clickjacking (was SAMEORIGIN, now stricter)
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com https://code.jquery.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https://*; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "frame-ancestors 'none';"  # Prevents embedding in iframes
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",  # Prevents leaking referrer info
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",  # Blocks camera/mic usage
}

    # Rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "100 per hour"
    RATELIMIT_STORAGE_URL = "memory://"

    # Flask configuration
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