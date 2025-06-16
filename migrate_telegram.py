"""
Database migration script to add Telegram support
Run this script to update your existing database schema
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, upgrade
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_migration_app():
    app = Flask(__name__)
    
    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db = SQLAlchemy(app)
    migrate = Migrate(app, db)
    
    return app, db, migrate

def run_migration():
    """Run database migration to add Telegram fields"""
    print("🔄 Running database migration for Telegram integration...")
    
    app, db, migrate = create_migration_app()
    
    with app.app_context():
        try:
            # Run the migration
            upgrade()
            print("✅ Database migration completed successfully!")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False
    
    return True

if __name__ == '__main__':
    success = run_migration()
    if not success:
        exit(1)
