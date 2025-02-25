from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get passwords from environment variables
tsel_password = os.getenv('TSEL_ADMIN_PASSWORD')
enom_password = os.getenv('ENOM_USER_PASSWORD')

# Validate passwords exist
if not tsel_password or not enom_password:
    print("Error: TSEL_ADMIN_PASSWORD and ENOM_USER_PASSWORD must be set in .env file")
    exit(1)

app = create_app()

with app.app_context():
    # Check if users already exist
    if User.query.filter_by(username='tsel_admin').first() is None:
        # Create Tsel admin user
        admin = User(
            username='tsel_admin',
            password_hash=generate_password_hash(tsel_password),
            role='tsel'
        )
        db.session.add(admin)
        print("Created TSEL admin user")
    
    if User.query.filter_by(username='enom_user').first() is None:
        # Create ENOM user
        enom = User(
            username='enom_user',
            password_hash=generate_password_hash(enom_password),
            role='enom'
        )
        db.session.add(enom)
        print("Created ENOM user")
    
    db.session.commit()
    print("Users created successfully") 
