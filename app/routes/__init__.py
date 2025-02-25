from app.routes.main import bp as main
from app.routes.auth import bp as auth 
from flask import redirect, url_for, flash
from flask_login import LoginManager

def init_routes(app):
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.routes import errors_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(errors_bp)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.models import User
        return User.query.get(int(user_id)) 