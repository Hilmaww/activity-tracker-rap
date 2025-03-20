import os
from app import create_app
from config import Config

config_class = Config.get_environment_config()

app = create_app(config=config_class)

if __name__ == '__main__':
    app.run(host=app.config['HOST'], port=app.config['PORT'])

