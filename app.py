import os
import secrets

from flask import Flask, jsonify, render_template, session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from extensions import db, migrate
from routes.admin import admin_bp
from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.store import store_bp
from services.cloudinary_service import build_image_url, configure_cloudinary


def create_app():
    """Create and configure the MundoMix Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    environment = app.config.get("ENVIRONMENT", "development").lower()
    configured_secret = os.getenv("SECRET_KEY", "").strip()
    if not configured_secret:
        if environment == "production":
            raise RuntimeError("SECRET_KEY no está configurada en producción.")
        configured_secret = secrets.token_hex(32)
    app.config["SECRET_KEY"] = configured_secret

    # In production Cloudinary credentials are mandatory. In development an
    # explicit missing configuration is allowed so the storefront can boot,
    # but image upload operations fail with a clear message.
    configure_cloudinary()

    db.init_app(app)
    migrate.init_app(app, db)

    @app.template_global("image_url")
    def image_url(public_id, secure_url="", width=None, height=None):
        try:
            return build_image_url(public_id, secure_url, width=width, height=height)
        except Exception:
            # Rendering must remain usable if Cloudinary is temporarily unavailable.
            app.logger.exception("Could not build Cloudinary image URL")
            return secure_url or ""

    app.register_blueprint(store_bp)
    app.register_blueprint(cart_bp, url_prefix="/carrito")
    app.register_blueprint(checkout_bp, url_prefix="/checkout")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "ok"}), 200
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("MundoMix health check failed")
            return jsonify({"status": "error"}), 503
        finally:
            db.session.remove()

    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_config():
        return jsonify({}), 200

    @app.context_processor
    def inject_globals():
        from models.settings import Setting

        settings = {}
        try:
            settings = {s.key: s.value for s in Setting.query.all()}
        except SQLAlchemyError:
            # A failed request must not be followed by another DB exception
            # while rendering the error page or a subsequent template.
            db.session.rollback()
            app.logger.exception("Could not load site settings for template globals")
        cart = session.get("cart", {})
        cart_count = 0
        for value in cart.values() if isinstance(cart, dict) else []:
            try:
                cart_count += max(0, int(value))
            except (TypeError, ValueError):
                continue
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
        # Roll back before rendering: the original exception may have left a
        # PostgreSQL transaction in an aborted state.
        db.session.rollback()
        app.logger.error("Unhandled MundoMix server error: %s", error, exc_info=True)
        return render_template("errors/500.html"), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=Config.DEBUG)
