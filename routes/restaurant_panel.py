from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4
from io import BytesIO
from PIL import Image
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from extensions import db
from models.order import Order, OrderItem
from models.restaurant import Restaurant, RestaurantCategory, RestaurantProduct, RestaurantHour
from routes.restaurant_auth import restaurant_required
from routes.restaurant_common import ARG_TZ, restaurant_is_open
from datetime import datetime, timedelta, timezone, time
from slugify import make_slug

restaurant_panel_bp = Blueprint("restaurant_panel", __name__)
ALLOWED = {"jpg", "jpeg", "png", "webp"}
STATUSES = ["Nuevo", "Contactado", "Confirmado", "Preparando", "Listo", "En camino", "Entregado", "Cancelado"]
ALLOWED_TRANSITIONS = {
    "Nuevo": {"Contactado", "Confirmado", "Cancelado"},
    "Contactado": {"Confirmado", "Cancelado"},
    "Confirmado": {"Preparando", "Cancelado"},
    "Preparando": {"Listo", "Cancelado"},
    "Listo": {"En camino", "Entregado", "Cancelado"},
    "En camino": {"Entregado", "Cancelado"},
    "Entregado": set(),
    "Cancelado": set(),
}


def current_restaurant():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return None
    return db.session.get(Restaurant, restaurant_id)




def _validated_time(value, label):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        hour, minute = value.split(":", 1)
        parsed = time(int(hour), int(minute))
    except (ValueError, TypeError):
        raise ValueError(f"Horario inválido para {label}.")
    return parsed.strftime("%H:%M")

def nonnegative_int(value, label):
    raw = "" if value is None else str(value).strip()
    if not raw:
        return 0
    try:
        number = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{label} debe ser un número entero.")
    if number < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    return number


def money(value):
    try:
        amount = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValueError("Ingresá un precio válido.")
    if amount < 0:
        raise ValueError("El precio no puede ser negativo.")
    return amount


def image_save(file, folder):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED:
        raise ValueError("Formato no permitido. Usá JPG, JPEG, PNG o WEBP.")
    raw = file.stream.read()
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("La imagen no puede superar 5 MB.")
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        file.stream.seek(0)
    except Exception as exc:
        raise ValueError("El archivo no contiene una imagen válida.") from exc
    filename = secure_filename(f"{uuid4().hex}.{ext}")
    target = Path(current_app.config["UPLOAD_FOLDER"]) / "restaurants" / folder
    target.mkdir(parents=True, exist_ok=True)
    file.save(target / filename)
    return f"restaurants/{folder}/{filename}"


def remove_saved_image(relative_path):
    if not relative_path:
        return
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        current_app.logger.warning("Rejected image deletion outside upload folder: %s", relative_path)
        return
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        current_app.logger.exception("Could not delete image: %s", relative_path)


def unique_category_slug(restaurant_id, name, current_id=None):
    base, slug, i = make_slug(name), make_slug(name), 2
    while RestaurantCategory.query.filter(RestaurantCategory.restaurant_id == restaurant_id,
                                          RestaurantCategory.slug == slug,
                                          RestaurantCategory.id != (current_id or -1)).first():
        slug = f"{base}-{i}"; i += 1
    return slug


def unique_product_slug(restaurant_id, name, current_id=None):
    base, slug, i = make_slug(name), make_slug(name), 2
    while RestaurantProduct.query.filter(RestaurantProduct.restaurant_id == restaurant_id,
                                         RestaurantProduct.slug == slug,
                                         RestaurantProduct.id != (current_id or -1)).first():
        slug = f"{base}-{i}"; i += 1
    return slug


def unique_sku(restaurant_id, sku, current_id=None):
    if not sku:
        sku = f"MM-{uuid4().hex[:8].upper()}"
    candidate, i = sku, 2
    while RestaurantProduct.query.filter(RestaurantProduct.restaurant_id == restaurant_id,
                                         RestaurantProduct.sku == candidate,
                                         RestaurantProduct.id != (current_id or -1)).first():
        candidate = f"{sku}-{i}"; i += 1
    return candidate


@restaurant_panel_bp.get("/comercio/panel")
@restaurant_required
def dashboard():
    restaurant = current_restaurant()
    if restaurant is None:
        session.pop("restaurant_user_id", None)
        session.pop("restaurant_id", None)
        return redirect(url_for("restaurant_auth.login"))
    now_local = datetime.now(ARG_TZ)
    local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    sales = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.restaurant_id == restaurant.id, Order.status != "Cancelado"
    ).scalar() or 0
    today_query = Order.query.filter(Order.restaurant_id == restaurant.id, Order.created_at >= start, Order.created_at < end)
    return render_template("restaurant/panel/dashboard.html", restaurant=restaurant,
        today_orders=today_query.count(),
        pending_orders=Order.query.filter(Order.restaurant_id == restaurant.id, Order.status.in_(["Nuevo", "Contactado"])).count(),
        sales=Decimal(str(sales)), products=RestaurantProduct.query.filter_by(restaurant_id=restaurant.id).count(),
        recent_orders=Order.query.filter_by(restaurant_id=restaurant.id).order_by(desc(Order.created_at)).limit(8).all(),
        is_open=restaurant_is_open(restaurant))


@restaurant_panel_bp.get("/comercio/panel/pedidos")
@restaurant_required
def orders():
    restaurant = current_restaurant()
    status = request.args.get("status", "")
    query = Order.query.filter_by(restaurant_id=restaurant.id)
    if status in STATUSES: query = query.filter_by(status=status)
    return render_template("restaurant/panel/orders.html", restaurant=restaurant, orders=query.order_by(desc(Order.created_at)).all(), statuses=STATUSES, selected_status=status)


@restaurant_panel_bp.route("/comercio/panel/pedidos/<int:id>", methods=["GET", "POST"])
@restaurant_required
def order_detail(id):
    restaurant = current_restaurant()
    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    if request.method == "POST":
        status = request.form.get("status")
        if status not in STATUSES:
            flash("Estado inválido.", "error")
        elif status != order.status and status not in ALLOWED_TRANSITIONS.get(order.status, set()):
            flash(f"No se puede pasar de {order.status} a {status}.", "error")
        elif status == "Confirmado" and not order.stock_deducted:
            order = db.session.execute(select(Order).where(Order.id == id, Order.restaurant_id == restaurant.id).with_for_update()).scalar_one_or_none()
            if order is None:
                return redirect(url_for("restaurant_panel.orders"))
            product_ids = sorted({oi.restaurant_product_id for oi in order.items if oi.restaurant_product_id})
            locked = {}
            for product_id in product_ids:
                locked[product_id] = db.session.execute(select(RestaurantProduct).where(RestaurantProduct.id == product_id, RestaurantProduct.restaurant_id == restaurant.id).with_for_update()).scalar_one_or_none()
            for oi in order.items:
                if oi.restaurant_product_id:
                    product = locked.get(oi.restaurant_product_id)
                    if not product or product.stock < oi.quantity:
                        db.session.rollback(); flash(f"Stock insuficiente para {oi.product_name_snapshot}.", "error")
                        order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
                        return render_template("restaurant/panel/order_detail.html", restaurant=restaurant, order=order, statuses=STATUSES)
                    product.stock -= oi.quantity
            order.status = status
            order.stock_deducted = True
            db.session.commit(); flash("Pedido confirmado y stock descontado.", "success")
        else:
            if status == order.status:
                flash("El pedido ya está en ese estado.", "success")
            else:
                if status == "Confirmado" and order.stock_deducted:
                    flash("Este pedido ya tenía el stock descontado; no se vuelve a descontar.", "success")
                order.status = status
                db.session.commit()
                flash("Pedido actualizado.", "success")
        order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    return render_template("restaurant/panel/order_detail.html", restaurant=restaurant, order=order, statuses=STATUSES)


@restaurant_panel_bp.route("/comercio/panel/configuracion", methods=["GET", "POST"])
@restaurant_required
def settings():
    restaurant = current_restaurant()
    if request.method == "POST":
        new_logo = None
        new_banner = None
        try:
            restaurant.name = request.form.get("name", "").strip() or restaurant.name
            restaurant.description = request.form.get("description", "").strip()
            restaurant.food_type = request.form.get("food_type", "Comida rápida").strip()
            restaurant.address = request.form.get("address", "").strip()
            restaurant.phone = request.form.get("phone", "").strip()
            restaurant.whatsapp = request.form.get("whatsapp", "").strip()
            restaurant.instagram = request.form.get("instagram", "").strip()
            restaurant.facebook = request.form.get("facebook", "").strip()
            restaurant.accept_orders_closed = "accept_orders_closed" in request.form
            restaurant.meta_title = request.form.get("meta_title", "").strip()
            restaurant.meta_description = request.form.get("meta_description", "").strip()
            logo = image_save(request.files.get("logo"), "logos")
            new_logo = logo
            banner = image_save(request.files.get("banner"), "banners")
            new_banner = banner
            old_logo, old_banner = restaurant.logo, restaurant.banner
            if logo: restaurant.logo = logo
            if banner: restaurant.banner = banner
            for day in range(7):
                hour = RestaurantHour.query.filter_by(restaurant_id=restaurant.id, weekday=day).first()
                if not hour:
                    hour = RestaurantHour(restaurant_id=restaurant.id, weekday=day); db.session.add(hour)
                hour.closed = f"closed_{day}" in request.form
                hour.start_time = _validated_time(request.form.get(f"start_{day}", "19:00"), f"día {day + 1}") or "19:00"
                hour.end_time = _validated_time(request.form.get(f"end_{day}", "00:00"), f"día {day + 1}") or "00:00"
                second_start = _validated_time(request.form.get(f"start2_{day}", ""), f"segundo turno del día {day + 1}")
                second_end = _validated_time(request.form.get(f"end2_{day}", ""), f"segundo turno del día {day + 1}")
                if bool(second_start) != bool(second_end):
                    raise ValueError(f"Completá inicio y fin del segundo turno del día {day + 1}, o dejalos vacíos.")
                hour.start_time_2 = second_start
                hour.end_time_2 = second_end
            db.session.commit()
            if logo and old_logo != logo: remove_saved_image(old_logo)
            if banner and old_banner != banner: remove_saved_image(old_banner)
            flash("Configuración guardada.", "success")
        except ValueError as exc:
            db.session.rollback()
            remove_saved_image(new_logo)
            remove_saved_image(new_banner)
            flash(str(exc), "error")
        except SQLAlchemyError:
            db.session.rollback()
            remove_saved_image(new_logo)
            remove_saved_image(new_banner)
            current_app.logger.exception("Restaurant settings database error")
            flash("No pudimos guardar la configuración. Intentá nuevamente.", "error")
        except Exception:
            db.session.rollback()
            remove_saved_image(new_logo)
            remove_saved_image(new_banner)
            current_app.logger.exception("Unexpected restaurant settings error")
            flash("No pudimos guardar la configuración. Intentá nuevamente.", "error")
    return render_template("restaurant/panel/settings.html", restaurant=restaurant)


@restaurant_panel_bp.route("/comercio/panel/categorias", methods=["GET", "POST"])
@restaurant_required
def categories():
    restaurant = current_restaurant()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre es obligatorio.", "error")
        else:
            try:
                duplicate = RestaurantCategory.query.filter_by(restaurant_id=restaurant.id, name=name).first()
                if duplicate:
                    raise ValueError("Ya existe una categoría con ese nombre.")
                db.session.add(RestaurantCategory(restaurant_id=restaurant.id, name=name, slug=unique_category_slug(restaurant.id, name), description=request.form.get("description", "").strip()))
                db.session.commit(); flash("Categoría creada.", "success")
            except ValueError as exc:
                db.session.rollback(); flash(str(exc), "error")
            except SQLAlchemyError:
                db.session.rollback(); current_app.logger.exception("Restaurant category database error"); flash("No pudimos crear la categoría.", "error")
    return render_template("restaurant/panel/categories.html", restaurant=restaurant, categories=RestaurantCategory.query.filter_by(restaurant_id=restaurant.id).order_by(RestaurantCategory.display_order, RestaurantCategory.name).all())


@restaurant_panel_bp.post("/comercio/panel/categorias/<int:id>/editar")
@restaurant_required
def category_edit(id):
    restaurant = current_restaurant(); item = RestaurantCategory.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    item.name = request.form.get("name", item.name).strip() or item.name
    duplicate = RestaurantCategory.query.filter(RestaurantCategory.restaurant_id == restaurant.id, RestaurantCategory.name == item.name, RestaurantCategory.id != item.id).first()
    if duplicate:
        flash("Ya existe otra categoría con ese nombre.", "error")
        return redirect(url_for("restaurant_panel.categories"))
    item.description = request.form.get("description", "").strip()
    item.slug = unique_category_slug(restaurant.id, item.name, item.id)
    db.session.commit(); flash("Categoría actualizada.", "success")
    return redirect(url_for("restaurant_panel.categories"))


@restaurant_panel_bp.post("/comercio/panel/categorias/<int:id>/toggle")
@restaurant_required
def category_toggle(id):
    restaurant = current_restaurant(); item = RestaurantCategory.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404(); item.active = not item.active; db.session.commit(); return redirect(url_for("restaurant_panel.categories"))


@restaurant_panel_bp.get("/comercio/panel/productos")
@restaurant_required
def products():
    restaurant = current_restaurant(); products = RestaurantProduct.query.filter_by(restaurant_id=restaurant.id).order_by(desc(RestaurantProduct.created_at)).all()
    return render_template("restaurant/panel/products.html", restaurant=restaurant, products=products)


@restaurant_panel_bp.route("/comercio/panel/productos/nuevo", methods=["GET", "POST"])
@restaurant_panel_bp.route("/comercio/panel/productos/<int:id>/editar", methods=["GET", "POST"])
@restaurant_required
def product_form(id=None):
    restaurant = current_restaurant(); item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first() if id else None
    if id and not item: return redirect(url_for("restaurant_panel.products"))
    categories = RestaurantCategory.query.filter_by(restaurant_id=restaurant.id).order_by(RestaurantCategory.name).all()
    if request.method == "POST":
        new_image = None
        try:
            name = request.form.get("name", "").strip()
            if not name: raise ValueError("El nombre es obligatorio.")
            if not item:
                item = RestaurantProduct(restaurant_id=restaurant.id, name=name, slug="temp", sku=unique_sku(restaurant.id, request.form.get("sku", "").strip()), price_delivery=0, price_pickup=0)
                db.session.add(item); db.session.flush()
            else:
                item.sku = unique_sku(restaurant.id, request.form.get("sku", "").strip(), item.id)
            item.name = name; item.slug = unique_product_slug(restaurant.id, name, item.id)
            item.description = request.form.get("description", "").strip()
            item.price_delivery = money(request.form.get("price_delivery", "0"))
            item.price_pickup = money(request.form.get("price_pickup", "0"))
            item.stock = nonnegative_int(request.form.get("stock", "0"), "El stock")
            category_id = request.form.get("category_id", type=int) or None
            if category_id is not None and not RestaurantCategory.query.filter_by(id=category_id, restaurant_id=restaurant.id).first():
                raise ValueError("La categoría seleccionada no pertenece a este local.")
            item.category_id = category_id
            item.featured = "featured" in request.form
            item.active = "active" in request.form
            image = image_save(request.files.get("image"), "products")
            new_image = image
            old_image = item.image
            if image: item.image = image
            db.session.commit()
            if image and old_image != image: remove_saved_image(old_image)
            flash("Producto guardado.", "success"); return redirect(url_for("restaurant_panel.products"))
        except ValueError as exc:
            db.session.rollback()
            remove_saved_image(new_image)
            flash(str(exc), "error")
        except IntegrityError:
            db.session.rollback()
            remove_saved_image(new_image)
            current_app.logger.exception("Restaurant product integrity error")
            flash("No pudimos guardar el producto. Revisá los datos e intentá nuevamente.", "error")
        except SQLAlchemyError:
            db.session.rollback()
            remove_saved_image(new_image)
            current_app.logger.exception("Restaurant product database error")
            flash("No pudimos guardar el producto. Intentá nuevamente.", "error")
        except Exception:
            db.session.rollback()
            remove_saved_image(new_image)
            current_app.logger.exception("Unexpected restaurant product error")
            flash("No pudimos guardar el producto. Intentá nuevamente.", "error")
    return render_template("restaurant/panel/product_form.html", restaurant=restaurant, product=item, categories=categories)


@restaurant_panel_bp.post("/comercio/panel/productos/<int:id>/toggle")
@restaurant_required
def product_toggle(id):
    restaurant = current_restaurant(); item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404(); item.active = not item.active; db.session.commit(); return redirect(url_for("restaurant_panel.products"))


@restaurant_panel_bp.post("/comercio/panel/configuracion/logo/eliminar")
@restaurant_required
def logo_delete():
    restaurant = current_restaurant()
    old = restaurant.logo
    restaurant.logo = None
    db.session.commit()
    remove_saved_image(old)
    flash("Logo eliminado.", "success")
    return redirect(url_for("restaurant_panel.settings"))


@restaurant_panel_bp.post("/comercio/panel/configuracion/banner/eliminar")
@restaurant_required
def banner_delete():
    restaurant = current_restaurant()
    old = restaurant.banner
    restaurant.banner = None
    db.session.commit()
    remove_saved_image(old)
    flash("Banner eliminado.", "success")
    return redirect(url_for("restaurant_panel.settings"))


@restaurant_panel_bp.post("/comercio/panel/productos/<int:id>/imagen/eliminar")
@restaurant_required
def product_image_delete(id):
    restaurant = current_restaurant()
    item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    old = item.image
    item.image = None
    db.session.commit()
    remove_saved_image(old)
    flash("Imagen eliminada.", "success")
    return redirect(url_for("restaurant_panel.product_form", id=id))


@restaurant_panel_bp.post("/comercio/panel/productos/<int:id>/eliminar")
@restaurant_required
def product_delete(id):
    restaurant = current_restaurant(); item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    if item.order_items:
        item.active = False; flash("El producto tiene pedidos históricos y fue desactivado en lugar de eliminarse.", "success")
    else:
        db.session.delete(item); flash("Producto eliminado.", "success")
    db.session.commit(); return redirect(url_for("restaurant_panel.products"))
