import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory, session, url_for
from sqlalchemy import text

from config import Config
from extensions import db, migrate
from routes.admin import admin_bp
from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.store import store_bp
from routes.restaurants import restaurants_bp
from routes.restaurant_cart import restaurant_cart_bp
from routes.restaurant_checkout import restaurant_checkout_bp
from routes.restaurant_auth import restaurant_auth_bp
from routes.restaurant_panel import restaurant_panel_bp
from routes.restaurant_menu import restaurant_menu_bp


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
        missing_cloudinary = [k for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET") if not os.getenv(k, "").strip()]
        if missing_cloudinary:
            raise RuntimeError("Faltan variables de Cloudinary en producción: " + ", ".join(missing_cloudinary))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    # Legacy upload storage is read-only compatibility for pre-Cloudinary assets.

    db.init_app(app)
    migrate.init_app(app, db)

    # Development can create missing tables for a fresh local install.
    # Production schema changes must go through Flask-Migrate/Alembic.
    if environment != "production":
        with app.app_context():
            db.create_all()

    app.register_blueprint(store_bp)
    app.register_blueprint(cart_bp, url_prefix="/carrito")
    app.register_blueprint(checkout_bp, url_prefix="/checkout")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(restaurants_bp)
    app.register_blueprint(restaurant_cart_bp)
    app.register_blueprint(restaurant_checkout_bp)
    app.register_blueprint(restaurant_auth_bp)
    app.register_blueprint(restaurant_panel_bp)
    app.register_blueprint(restaurant_menu_bp)

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

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.template_filter("arg_dt")
    def arg_dt_filter(value):
        from routes.restaurant_common import ARG_TZ
        if not value: return ""
        return value.replace(tzinfo=__import__("datetime").timezone.utc).astimezone(ARG_TZ).strftime("%d/%m/%Y %H:%M")

    @app.template_filter("fromjson")
    def fromjson_filter(value):
        import json
        try:
            return json.loads(value or "[]")
        except (TypeError, ValueError):
            return []

    @app.template_global("image_src")
    def image_src(cloudinary_url=None, legacy_path=None):
        """Return a Cloudinary HTTPS URL for new assets, with legacy fallback."""
        value = cloudinary_url or legacy_path
        if not value:
            return ""
        if str(value).startswith(("https://", "http://")):
            return value
        return url_for("uploaded_file", filename=value)

    @app.context_processor
    def inject_globals():
        from models.settings import Setting

        settings = {s.key: s.value for s in Setting.query.all()}
        cart = session.get("cart", {})
        cart_count = sum(int(v) for v in cart.values()) if cart else 0
        restaurant_cart = session.get("restaurant_cart", {})
        restaurant_cart_count = 0
        if restaurant_cart:
            for local in restaurant_cart.values():
                for line in local.values():
                    if isinstance(line, dict):
                        try: restaurant_cart_count += max(0, int(line.get("quantity", 0)))
                        except (TypeError, ValueError): pass
                    else:
                        try: restaurant_cart_count += max(0, int(line))
                        except (TypeError, ValueError): pass
        return {"site_settings": settings, "cart_count": cart_count, "restaurant_cart_count": restaurant_cart_count}

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
