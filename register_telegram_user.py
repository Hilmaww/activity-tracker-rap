"""
Helper script to register Telegram users with existing ENOM accounts
"""

import sys
from app import create_app
from models import db, User
from datetime import datetime

def register_telegram_user(username, telegram_id, telegram_username=None, 
                          telegram_first_name=None, telegram_last_name=None):
    """Register a Telegram ID with an existing user account"""
    
    app = create_app()
    
    with app.app_context():
        try:
            # Find existing user
            user = User.query.filter_by(username=username).first()
            
            if not user:
                print(f"❌ User '{username}' not found in database")
                return False
            
            if user.telegram_id:
                print(f"⚠️ User '{username}' already has Telegram ID: {user.telegram_id}")
                return False
            
            # Update user with Telegram info
            user.telegram_id = str(telegram_id)
            user.telegram_username = telegram_username
            user.telegram_first_name = telegram_first_name
            user.telegram_last_name = telegram_last_name
            user.telegram_enabled = True
            user.telegram_registered_at = datetime.utcnow()
            
            db.session.commit()
            
            print(f"✅ Successfully registered Telegram ID {telegram_id} for user '{username}'")
            return True
            
        except Exception as e:
            print(f"❌ Error registering user: {e}")
            db.session.rollback()
            return False

def list_telegram_users():
    """List all users with Telegram integration enabled"""
    
    app = create_app()
    
    with app.app_context():
        users = User.query.filter(User.telegram_enabled == True).all()
        
        if not users:
            print("📭 No users with Telegram integration found")
            return
        
        print("👥 Users with Telegram Integration:")
        print("-" * 50)
        
        for user in users:
            print(f"Username: {user.username}")
            print(f"Role: {user.role.value if user.role else 'N/A'}")
            print(f"Telegram ID: {user.telegram_id}")
            print(f"Telegram Username: @{user.telegram_username or 'N/A'}")
            print(f"Full Name: {user.telegram_first_name or ''} {user.telegram_last_name or ''}".strip())
            print(f"Registered: {user.telegram_registered_at}")
            print("-" * 50)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python register_telegram_user.py list")
        print("  python register_telegram_user.py register <username> <telegram_id> [telegram_username] [first_name] [last_name]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'list':
        list_telegram_users()
    elif command == 'register':
        if len(sys.argv) < 4:
            print("❌ Missing required arguments: username and telegram_id")
            sys.exit(1)
        
        username = sys.argv[2]
        telegram_id = sys.argv[3]
        telegram_username = sys.argv[4] if len(sys.argv) > 4 else None
        first_name = sys.argv[5] if len(sys.argv) > 5 else None
        last_name = sys.argv[6] if len(sys.argv) > 6 else None
        
        success = register_telegram_user(username, telegram_id, telegram_username, first_name, last_name)
        if not success:
            sys.exit(1)
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
