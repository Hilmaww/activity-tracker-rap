from flask import Blueprint

bp = Blueprint('alarms', __name__, url_prefix='/alarms')

from app.routes.alarms import routes 