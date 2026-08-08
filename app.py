from flask import Flask
from flask_login import LoginManager

from config import Config
from database.models import db, User
from services.google_auth import init_google_oauth


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    init_google_oauth(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login_page"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)

    # Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.board import board_bp
    from routes.team import team_bp
    from routes.analytics import analytics_bp
    from routes.settings import settings_bp
    from routes.chat import chat_bp
    from routes.video import video_bp
    from routes.mail import mail_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(board_bp)
    app.register_blueprint(team_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(mail_bp)

    @app.context_processor
    def inject_sidebar_profile():
        """Makes the current user's workspace role available to every template
        (used by the sidebar profile card in base.html) without every route
        having to look it up and pass it in separately."""
        from flask_login import current_user
        from database.models import WorkspaceMember

        if not current_user.is_authenticated:
            return {}

        membership = WorkspaceMember.query.filter_by(user_id=current_user.id).first()
        return {"sidebar_role": membership.role if membership else None}

    with app.app_context():
        db.create_all()  # dev convenience; use Flask-Migrate for real changes later

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
