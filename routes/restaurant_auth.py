from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from models.restaurant import RestaurantUser

restaurant_auth_bp = Blueprint("restaurant_auth", __name__)


def _safe_next(value):
    """Only allow local relative redirects after login."""
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def restaurant_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get("restaurant_user_id")
        if not user_id:
            return redirect(url_for("restaurant_auth.login", next=request.path))
        user = RestaurantUser.query.filter_by(id=user_id).first()
        if not user or not user.active or not user.restaurant or not user.restaurant.active:
            session.pop("restaurant_user_id", None)
            session.pop("restaurant_id", None)
            return redirect(url_for("restaurant_auth.login", next=request.path))
        # Never trust a stale restaurant_id from the client session.
        session["restaurant_id"] = user.restaurant_id
        return fn(*args, **kwargs)
    return wrapper


@restaurant_auth_bp.route("/comercio/login", methods=["GET", "POST"])
def login():
    next_url = _safe_next(request.args.get("next"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = RestaurantUser.query.filter_by(username=username).first()
        if user and user.active and check_password_hash(user.password_hash, password) and user.restaurant and user.restaurant.active:
            session.clear()
            session["restaurant_user_id"] = user.id
            session["restaurant_id"] = user.restaurant_id
            return redirect(next_url or url_for("restaurant_panel.dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("restaurant/login.html")


@restaurant_auth_bp.get("/comercio/logout")
def logout():
    session.pop("restaurant_user_id", None)
    session.pop("restaurant_id", None)
    return redirect(url_for("restaurant_auth.login"))
