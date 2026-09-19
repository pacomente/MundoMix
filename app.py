import os
import secrets

from flask import Flask, jsonify, render_template, session
from sqlalchemy import text

from config import Config
from extensions import db, migrate
from routes.admin import admin_bp
from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.store import store_bp


def create_app():
    """Create and configure the MundoMix Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    environment = app.config.get("ENVIRONMENT", "development").lower()
    configured_secret = os.getenv("SECRET_KEY", "").strip()
    if not configured_secret:
        if environment == "production":
            raise RuntimeError(
                "SECRET_KEY no está configurada. Definí una SECRET_KEY segura en .env "
                "o en las variables de entorno antes de iniciar MundoMix en producción."
            )
        # Development only: generate an ephemeral secret instead of using a predictable value.
        configured_secret = secrets.token_hex(32)
    app.config["SECRET_KEY"] = configured_secret

    if environment == "production":
        missing_cloudinary = [
            key for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
            if not app.config.get(key)
        ]
        if missing_cloudinary:
            raise RuntimeError(
                "Faltan variables de Cloudinary en producción: " + ", ".join(missing_cloudinary)
            )

    from pathlib import Path
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(store_bp)
    app.register_blueprint(cart_bp, url_prefix="/carrito")
    app.register_blueprint(checkout_bp, url_prefix="/checkout")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.get("/health")
    def health():
        # Check the database without exposing connection details.
        try:
            db.session.execute(text("SELECT 1"))
            db.session.remove()
            return jsonify({"status": "ok"}), 200
        except Exception:
            app.logger.exception("MundoMix health check failed")
            db.session.rollback()
            db.session.remove()
            return jsonify({"status": "error"}), 503

    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_config():
        """Public minimal response requested automatically by Chrome DevTools."""
        return jsonify({}), 200

    @app.context_processor
    def inject_globals():
        from models.settings import Setting

        try:
            settings = {s.key: s.value for s in Setting.query.all()}
        except Exception:
            # A previous PostgreSQL error can leave the transaction aborted.
            # Roll back before the error page or another request performs a query.
            db.session.rollback()
            app.logger.exception("Failed to load site settings in context processor")
            settings = {}
        cart = session.get("cart", {})
        cart_count = sum(int(v) for v in cart.values()) if cart else 0
        return {"site_settings": settings, "cart_count": cart_count}

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return render_template("errors/405.html"), 405

    @app.errorhandler(500)
    def server_error(error):
        app.logger.error(
            "Unhandled MundoMix server error: %s",
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        return render_template("errors/500.html"), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=Config.DEBUG)
