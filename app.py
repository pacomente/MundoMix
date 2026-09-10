import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory, session

from config import Config
from extensions import db
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

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"], "products").mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"], "banners").mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    # Safe startup initialization: creates only missing tables and never drops data.
    with app.app_context():
        db.create_all()

    app.register_blueprint(store_bp)
    app.register_blueprint(cart_bp, url_prefix="/carrito")
    app.register_blueprint(checkout_bp, url_prefix="/checkout")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_config():
        """Public minimal response requested automatically by Chrome DevTools."""
        return jsonify({}), 200

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.context_processor
    def inject_globals():
        from models.settings import Setting

        settings = {s.key: s.value for s in Setting.query.all()}
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
