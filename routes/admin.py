from functools import wraps
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from urllib.parse import urlsplit
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from extensions import db
from models import Product, Category, Banner, Order, OrderItem, Admin, Setting, Restaurant, RestaurantUser, RestaurantCategory, RestaurantProduct, RestaurantHour
from slugify import make_slug

admin_bp = Blueprint("admin", __name__)
STATUSES = ["Nuevo", "Contactado", "Confirmado", "Preparando", "Listo", "En camino", "Entregado", "Cancelado"]
ALLOWED = {"jpg", "jpeg", "png", "webp"}


def _safe_next(value):
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def save_image(file, folder):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED:
        raise ValueError("Formato de imagen no permitido. Usá JPG, JPEG, PNG o WEBP.")
    name = f"{uuid4().hex}.{ext}"
    target = Path(current_app.config["UPLOAD_FOLDER"]) / folder
    target.mkdir(parents=True, exist_ok=True)
    file.save(target / secure_filename(name))
    return f"{folder}/{name}"


def parse_money(value):
    try:
        amount = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValueError("Ingresá un precio válido.")
    if amount < 0:
        raise ValueError("Los precios no pueden ser negativos.")
    return amount


def unique_slug(name, current_id=None):
    base = make_slug(name)
    slug = base
    i = 2
    while True:
        query = Product.query.filter_by(slug=slug)
        if current_id:
            query = query.filter(Product.id != current_id)
        if not query.first():
            return slug
        slug = f"{base}-{i}"
        i += 1


def unique_restaurant_slug(name, current_id=None):
    base = make_slug(name) or "local"
    slug = base
    i = 2
    while True:
        query = Restaurant.query.filter_by(slug=slug)
        if current_id:
            query = query.filter(Restaurant.id != current_id)
        if not query.first():
            return slug
        slug = f"{base}-{i}"
        i += 1

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.clear()
            session["admin_id"] = admin.id
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("admin/login.html")

@admin_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))

@admin_bp.get("/")
@admin_bp.get("")
@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    sales = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(Order.status != "Cancelado").scalar() or 0
    best = (db.session.query(
        OrderItem.product_name_snapshot,
        func.sum(OrderItem.quantity).label("qty")
    )
    .join(Order, Order.id == OrderItem.order_id)
    .filter(Order.status != "Cancelado")
    .group_by(OrderItem.product_name_snapshot)
    .order_by(desc("qty"))
    .limit(5)
    .all())
    return render_template("admin/dashboard.html", total_products=Product.query.count(),
        active_products=Product.query.filter_by(active=True).count(), out_stock=Product.query.filter(Product.stock <= 0).count(),
        featured_products=Product.query.filter_by(featured=True, active=True).count(),
        total_orders=Order.query.count(), new_orders=Order.query.filter_by(status="Nuevo").count(),
        confirmed_orders=Order.query.filter_by(status="Confirmado").count(),
        delivered_orders=Order.query.filter_by(status="Entregado").count(), sales=Decimal(str(sales)),
        recent_orders=Order.query.order_by(desc(Order.created_at)).limit(8).all(), best_products=best)

@admin_bp.route("/productos")
@admin_bp.route("/products")
@admin_required
def products():
    return render_template("admin/products.html", products=Product.query.order_by(desc(Product.created_at)).all())

@admin_bp.route("/productos/nuevo", methods=["GET", "POST"])
@admin_bp.route("/productos/<int:id>/editar", methods=["GET", "POST"])
@admin_required
def product_form(id=None):
    item = Product.query.get(id) if id else None
    categories = Category.query.order_by(Category.name).all()
    if id and not item:
        return redirect(url_for("admin.products"))
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            sku = request.form.get("sku", "").strip()
            if not name or not sku:
                raise ValueError("Nombre y SKU son obligatorios.")
            duplicate = Product.query.filter(Product.sku == sku, Product.id != (item.id if item else -1)).first()
            if duplicate:
                raise ValueError("Ese SKU ya existe.")
            stock = request.form.get("stock", 0, type=int)
            if stock < 0:
                raise ValueError("El stock no puede ser negativo.")
            if not item:
                item = Product(name=name, sku=sku, slug="temp", price_delivery=0, price_pickup=0)
                db.session.add(item)
                db.session.flush()
            item.name = name
            item.sku = sku
            item.slug = unique_slug(name, item.id)
            item.description = request.form.get("description", "").strip()
            item.price_delivery = parse_money(request.form.get("price_delivery", "0"))
            item.price_pickup = parse_money(request.form.get("price_pickup", "0"))
            item.stock = stock
            item.category_id = request.form.get("category_id", type=int) or None
            item.featured = "featured" in request.form
            item.active = "active" in request.form
            image = save_image(request.files.get("image"), "products")
            if image:
                item.image = image
            extra = []
            for file in request.files.getlist("additional_images"):
                saved = save_image(file, "products")
                if saved:
                    extra.append(saved)
            if extra:
                item.additional_images = ",".join(extra)
            db.session.commit()
            flash("Producto guardado correctamente.", "success")
            return redirect(url_for("admin.products"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("admin/product_form.html", product=item, categories=categories)

@admin_bp.post("/productos/<int:id>/eliminar")
@admin_required
def product_delete(id):
    item = Product.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash("Producto eliminado.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.post("/productos/<int:id>/imagen/eliminar")
@admin_required
def product_image_delete(id):
    item = Product.query.get_or_404(id)
    item.image = None
    db.session.commit(); flash("Imagen principal eliminada.", "success")
    return redirect(url_for("admin.product_form", id=id))

@admin_bp.post("/productos/<int:id>/imagenes/eliminar/<int:index>")
@admin_required
def product_extra_image_delete(id, index):
    item = Product.query.get_or_404(id)
    images = item.image_list
    if 0 <= index < len(images):
        images.pop(index)
        item.additional_images = ",".join(images)
        db.session.commit(); flash("Imagen adicional eliminada.", "success")
    return redirect(url_for("admin.product_form", id=id))

@admin_bp.post("/productos/<int:id>/toggle")
@admin_required
def product_toggle(id):
    item = Product.query.get_or_404(id)
    item.active = not item.active
    db.session.commit()
    flash(f"Producto {'activado' if item.active else 'desactivado'}.", "success")
    return redirect(url_for("admin.products"))

@admin_bp.route("/categorias", methods=["GET", "POST"])
@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre es obligatorio.", "error")
        elif Category.query.filter_by(name=name).first():
            flash("La categoría ya existe.", "error")
        else:
            base_slug = make_slug(name)
            slug = base_slug
            i = 2
            while Category.query.filter_by(slug=slug).first():
                slug = f"{base_slug}-{i}"
                i += 1
            try:
                db.session.add(Category(name=name, slug=slug, description=request.form.get("description", "").strip(), active=True))
                db.session.commit()
                flash("Categoría creada.", "success")
            except Exception as exc:
                db.session.rollback()
                flash(str(exc), "error")
    return render_template("admin/categories.html", categories=Category.query.order_by(Category.name).all())

@admin_bp.post("/categorias/<int:id>/editar")
@admin_required
def category_edit(id):
    item = Category.query.get_or_404(id)
    name = request.form.get("name", item.name).strip()
    if not name:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("admin.categories"))
    duplicate = Category.query.filter(Category.name == name, Category.id != item.id).first()
    if duplicate:
        flash("Ya existe otra categoría con ese nombre.", "error")
        return redirect(url_for("admin.categories"))
    try:
        item.name = name
        item.description = request.form.get("description", "").strip()
        base_slug = make_slug(name)
        slug = base_slug
        i = 2
        while Category.query.filter(Category.slug == slug, Category.id != item.id).first():
            slug = f"{base_slug}-{i}"
            i += 1
        item.slug = slug
        image = save_image(request.files.get("image"), "categories")
        if image:
            item.image = image
        db.session.commit()
        flash("Categoría actualizada.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.categories"))

@admin_bp.post("/categorias/<int:id>/toggle")
@admin_required
def category_toggle(id):
    item = Category.query.get_or_404(id); item.active = not item.active; db.session.commit()
    flash(f"Categoría {'activada' if item.active else 'desactivada'}.", "success")
    return redirect(url_for("admin.categories"))

@admin_bp.post("/categorias/<int:id>/eliminar")
@admin_required
def category_delete(id):
    item = Category.query.get_or_404(id)
    for product in item.products:
        product.category_id = None
    db.session.delete(item); db.session.commit()
    flash("Categoría eliminada; los productos quedaron sin categoría.", "success")
    return redirect(url_for("admin.categories"))

@admin_bp.route("/banners", methods=["GET", "POST"])
@admin_required
def banners():
    if request.method == "POST":
        try:
            image = save_image(request.files.get("image"), "banners")
            if not image:
                raise ValueError("La imagen del banner es obligatoria.")
            db.session.add(Banner(title=request.form.get("title", "").strip(), subtitle=request.form.get("subtitle", "").strip(),
                image=image, button_text=request.form.get("button_text", "").strip(), button_url=request.form.get("button_url", "").strip(),
                display_order=request.form.get("display_order", 0, type=int), active="active" in request.form))
            db.session.commit(); flash("Banner creado.", "success")
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "error")
    return render_template("admin/banners.html", banners=Banner.query.order_by(Banner.display_order, Banner.id).all())

@admin_bp.post("/banners/<int:id>/toggle")
@admin_required
def banner_toggle(id):
    item = Banner.query.get_or_404(id); item.active = not item.active; db.session.commit()
    flash("Banner actualizado.", "success"); return redirect(url_for("admin.banners"))

@admin_bp.post("/banners/<int:id>/editar")
@admin_required
def banner_edit(id):
    item = Banner.query.get_or_404(id)
    item.title = request.form.get("title", "").strip(); item.subtitle = request.form.get("subtitle", "").strip()
    item.button_text = request.form.get("button_text", "").strip(); item.button_url = request.form.get("button_url", "").strip()
    item.display_order = request.form.get("display_order", 0, type=int); item.active = "active" in request.form
    image = save_image(request.files.get("image"), "banners")
    if image: item.image = image
    db.session.commit(); flash("Banner actualizado.", "success"); return redirect(url_for("admin.banners"))

@admin_bp.post("/banners/<int:id>/eliminar")
@admin_required
def banner_delete(id):
    db.session.delete(Banner.query.get_or_404(id)); db.session.commit(); flash("Banner eliminado.", "success")
    return redirect(url_for("admin.banners"))

@admin_bp.get("/pedidos")
@admin_bp.get("/orders")
@admin_required
def orders():
    status = request.args.get("status", "")
    query = Order.query
    if status in STATUSES: query = query.filter_by(status=status)
    orders_list = query.options(joinedload(Order.restaurant)).order_by(desc(Order.created_at)).all()
    return render_template("admin/orders.html", orders=orders_list, statuses=STATUSES, selected_status=status)

@admin_bp.route("/pedidos/<int:id>", methods=["GET", "POST"])
@admin_required
def order_detail(id):
    if request.method == "POST":
        # Lock the order and the affected products inside one transaction.
        # PostgreSQL then prevents two concurrent confirmations from both
        # passing the stock check with the same inventory.
        order = db.session.execute(
            select(Order).where(Order.id == id).with_for_update()
        ).scalar_one_or_none()
        if order is None:
            return redirect(url_for("admin.orders"))
        new_status = request.form.get("status")
        if new_status not in STATUSES:
            flash("Estado inválido.", "error")
        elif new_status == "Confirmado" and not order.stock_deducted:
            product_ids = sorted({oi.product_id for oi in order.items if oi.product_id})
            locked_products = {}
            for product_id in product_ids:
                product = db.session.execute(
                    select(Product).where(Product.id == product_id).with_for_update()
                ).scalar_one_or_none()
                locked_products[product_id] = product

            for oi in order.items:
                if oi.product_id:
                    product = locked_products.get(oi.product_id)
                    if not product or product.stock < oi.quantity:
                        db.session.rollback()
                        flash(f"Stock insuficiente para {oi.product_name_snapshot}.", "error")
                        order = Order.query.get_or_404(id)
                        return render_template("admin/order_detail.html", order=order, statuses=STATUSES)
                    product.stock -= oi.quantity
                elif oi.restaurant_product_id:
                    product_query = select(RestaurantProduct).where(RestaurantProduct.id == oi.restaurant_product_id).with_for_update()
                    if order.restaurant_id is not None:
                        product_query = product_query.where(RestaurantProduct.restaurant_id == order.restaurant_id)
                    product = db.session.execute(product_query).scalar_one_or_none()
                    if not product or product.stock < oi.quantity:
                        db.session.rollback()
                        flash(f"Stock insuficiente para {oi.product_name_snapshot}.", "error")
                        order = Order.query.get_or_404(id)
                        return render_template("admin/order_detail.html", order=order, statuses=STATUSES)
                    product.stock -= oi.quantity
            order.status = new_status
            order.stock_deducted = True
            db.session.commit()
            flash("Pedido confirmado y stock descontado.", "success")
        elif order.status == "Confirmado" and new_status != "Confirmado":
            # Stock is intentionally not restored automatically; this avoids double-restocking and keeps auditability simple.
            order.status = new_status
            db.session.commit()
            flash("Estado actualizado. El stock no se repone automáticamente.", "success")
        else:
            order.status = new_status
            db.session.commit()
            flash("Pedido actualizado.", "success")
    else:
        order = Order.query.get_or_404(id)
    return render_template("admin/order_detail.html", order=order, statuses=STATUSES)


@admin_bp.route("/locales", methods=["GET", "POST"])
@admin_bp.route("/restaurants", methods=["GET", "POST"])
@admin_required
def restaurants():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not name or not username or not password:
                raise ValueError("Nombre, usuario y contraseña son obligatorios.")
            if RestaurantUser.query.filter_by(username=username).first():
                raise ValueError("Ese usuario ya existe.")
            restaurant = Restaurant(name=name, slug=unique_restaurant_slug(name), description=request.form.get("description", "").strip(), food_type=request.form.get("food_type", "Comida rápida").strip(), address=request.form.get("address", "").strip(), phone=request.form.get("phone", "").strip(), whatsapp=request.form.get("whatsapp", "").strip(), active=True)
            db.session.add(restaurant); db.session.flush()
            db.session.add(RestaurantUser(restaurant_id=restaurant.id, username=username, password_hash=generate_password_hash(password)))
            for day in range(7):
                db.session.add(RestaurantHour(restaurant_id=restaurant.id, weekday=day, closed=True))
            db.session.commit(); flash("Local creado con acceso al panel.", "success")
        except ValueError as exc:
            db.session.rollback(); flash(str(exc), "error")
        except IntegrityError:
            db.session.rollback(); current_app.logger.exception("Restaurant creation integrity error"); flash("No pudimos crear el local. Revisá el usuario y los datos e intentá nuevamente.", "error")
        except SQLAlchemyError:
            db.session.rollback(); current_app.logger.exception("Restaurant creation database error"); flash("No pudimos crear el local. Intentá nuevamente.", "error")
        except Exception:
            db.session.rollback(); current_app.logger.exception("Unexpected restaurant creation error"); flash("No pudimos crear el local. Intentá nuevamente.", "error")
    return render_template("admin/restaurants.html", restaurants=Restaurant.query.order_by(Restaurant.name).all())


@admin_bp.route("/locales/<int:id>/editar", methods=["GET", "POST"])
@admin_required
def restaurant_edit(id):
    restaurant = Restaurant.query.get_or_404(id)
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            if not name: raise ValueError("El nombre es obligatorio.")
            restaurant.name = name; restaurant.slug = unique_restaurant_slug(name, restaurant.id)
            restaurant.description = request.form.get("description", "").strip(); restaurant.food_type = request.form.get("food_type", "Comida rápida").strip(); restaurant.address = request.form.get("address", "").strip(); restaurant.phone = request.form.get("phone", "").strip(); restaurant.whatsapp = request.form.get("whatsapp", "").strip(); restaurant.instagram = request.form.get("instagram", "").strip(); restaurant.facebook = request.form.get("facebook", "").strip(); restaurant.active = "active" in request.form; restaurant.accept_orders_closed = "accept_orders_closed" in request.form
            new_username = request.form.get("username", "").strip(); new_password = request.form.get("password", "")
            user = restaurant.users[0] if restaurant.users else None
            if new_username:
                other = RestaurantUser.query.filter(RestaurantUser.username == new_username, RestaurantUser.id != (user.id if user else -1)).first()
                if other: raise ValueError("Ese usuario ya existe.")
                if user: user.username = new_username
            if new_password:
                if not user:
                    user = RestaurantUser(restaurant_id=restaurant.id, username=new_username or f"local_{restaurant.id}", password_hash=generate_password_hash(new_password)); db.session.add(user)
                else: user.password_hash = generate_password_hash(new_password)
            db.session.commit(); flash("Local actualizado.", "success")
        except ValueError as exc:
            db.session.rollback(); flash(str(exc), "error")
        except IntegrityError:
            db.session.rollback(); current_app.logger.exception("Restaurant edit integrity error"); flash("No pudimos actualizar el local. Revisá los datos e intentá nuevamente.", "error")
        except SQLAlchemyError:
            db.session.rollback(); current_app.logger.exception("Restaurant edit database error"); flash("No pudimos actualizar el local. Intentá nuevamente.", "error")
        except Exception:
            db.session.rollback(); current_app.logger.exception("Unexpected restaurant edit error"); flash("No pudimos actualizar el local. Intentá nuevamente.", "error")
    return render_template("admin/restaurant_form.html", restaurant=restaurant, user=restaurant.users[0] if restaurant.users else None)


@admin_bp.post("/locales/<int:id>/toggle")
@admin_required
def restaurant_toggle(id):
    restaurant = Restaurant.query.get_or_404(id); restaurant.active = not restaurant.active; db.session.commit(); flash(f"Local {'activado' if restaurant.active else 'desactivado'}.", "success"); return redirect(url_for("admin.restaurants"))


@admin_bp.get("/locales/<int:id>/panel")
@admin_required
def restaurant_panel_link(id):
    restaurant = Restaurant.query.get_or_404(id)
    return redirect(url_for("restaurants.detail", slug=restaurant.slug))

@admin_bp.route("/configuracion", methods=["GET", "POST"])
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    keys = ["store_name", "whatsapp_number", "description", "contact", "social", "instagram", "facebook", "pickup_address", "business_hours", "delivery_info"]
    if request.method == "POST":
        for key in keys:
            row = Setting.query.filter_by(key=key).first()
            if not row:
                row = Setting(key=key); db.session.add(row)
            row.value = request.form.get(key, "").strip()
        db.session.commit(); flash("Configuración guardada.", "success")
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/settings.html", settings=settings)
