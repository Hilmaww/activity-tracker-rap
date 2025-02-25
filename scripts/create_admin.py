from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # Create Tsel admin user
    admin = User(
        username='tsel_admin',
        password_hash=generate_password_hash('your_secure_password'),
        role='tsel'
    )
    db.session.add(admin)
    
    # Create ENOM user
    enom = User(
        username='enom_user',
        password_hash=generate_password_hash('enom_secure_password'),
        role='enom'
    )
    db.session.add(enom)
    db.session.commit() 