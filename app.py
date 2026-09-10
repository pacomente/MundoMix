from pathlib import Path
from flask import Flask, send_from_directory, session, jsonify, render_template
from config import Config
from extensions import db
from routes.store import store_bp
from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.admin import admin_bp


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    # Create missing tables without touching existing data. This also lets a fresh
    # installation render the admin even before running init_db.py.
    with app.app_context():
        db.create_all()
    app.register_blueprint(store_bp)
    app.register_blueprint(cart_bp, url_prefix="/carrito")
    app.register_blueprint(checkout_bp, url_prefix="/checkout")
    app.register_blueprint(admin_bp, url_prefix="/admin")

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
        return {"site_settings": settings, "cart_count": sum(int(v) for v in cart.values()) if cart else 0}

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
        app.logger.exception("Unhandled MundoMix server error", exc_info=error)
        return render_template("errors/500.html"), 500

    return app

if __name__ == "__main__":
    create_app().run(debug=True)
