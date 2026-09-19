from functools import wraps
from decimal import Decimal, InvalidOperation
import json
from uuid import uuid4

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash
from sqlalchemy import desc, func, select
from extensions import db
from models import Product, Category, Banner, Order, OrderItem, Admin, Setting
from services.cloudinary_service import upload_image, delete_image
from slugify import make_slug

admin_bp = Blueprint("admin", __name__)
STATUSES = ["Nuevo", "Contactado", "Confirmado", "Preparando", "Listo", "En camino", "Entregado", "Cancelado"]


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


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


def _public_ids_for_product(item):
    return [x for x in [item.cloudinary_public_id] + item.additional_public_id_list if x]


def _cleanup_uploaded(uploaded):
    for result in uploaded:
        try:
            delete_image(result.get("public_id"))
        except Exception:
            current_app.logger.exception("Cloudinary cleanup failed for %s", result.get("public_id"))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.clear()
            session["admin_id"] = admin.id
            return redirect(request.args.get("next") or url_for("admin.dashboard"))
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
    best = (db.session.query(OrderItem.product_name_snapshot, func.sum(OrderItem.quantity).label("qty"))
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.status != "Cancelado")
            .group_by(OrderItem.product_name_snapshot)
            .order_by(desc("qty")).limit(5).all())
    return render_template("admin/dashboard.html", total_products=Product.query.count(),
        active_products=Product.query.filter_by(active=True).count(), out_stock=Product.query.filter(Product.stock <= 0).count(),
        featured_products=Product.query.filter_by(featured=True, active=True).count(), total_orders=Order.query.count(),
        new_orders=Order.query.filter_by(status="Nuevo").count(), confirmed_orders=Order.query.filter_by(status="Confirmado").count(),
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
        uploaded = []
        old_main_public_id = item.cloudinary_public_id if item else None
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

            is_new = item is None
            if is_new:
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

            main_file = request.files.get("image")
            if main_file and main_file.filename:
                result = upload_image(main_file, "mundomix/products", public_id=f"product-{item.id}-main-{uuid4().hex}")
                uploaded.append(result)
                item.image = result["secure_url"]
                item.cloudinary_public_id = result["public_id"]

            existing_urls = item.image_list
            existing_public_ids = item.additional_public_id_list
            new_urls, new_public_ids = [], []
            for file in request.files.getlist("additional_images"):
                if not file or not file.filename:
                    continue
                result = upload_image(file, "mundomix/products", public_id=f"product-{item.id}-extra-{uuid4().hex}")
                uploaded.append(result)
                new_urls.append(result["secure_url"])
                new_public_ids.append(result["public_id"])

            if new_urls:
                item.additional_images = ",".join(existing_urls + new_urls)
                item.additional_image_public_ids = json.dumps(existing_public_ids + new_public_ids)
            elif is_new and not item.additional_images:
                item.additional_images = ""
                item.additional_image_public_ids = "[]"

            db.session.commit()

            # Only delete the old image after the new reference is safely committed.
            if main_file and main_file.filename and old_main_public_id and old_main_public_id != item.cloudinary_public_id:
                try:
                    delete_image(old_main_public_id)
                except Exception:
                    current_app.logger.exception("Old product image cleanup failed for product %s", item.id)
                    flash("Producto guardado, pero no se pudo limpiar la imagen anterior de Cloudinary.", "error")

            flash("Producto guardado correctamente.", "success")
            return redirect(url_for("admin.products"))
        except Exception as exc:
            db.session.rollback()
            _cleanup_uploaded(uploaded)
            flash(str(exc), "error")

    return render_template("admin/product_form.html", product=item, categories=categories)


@admin_bp.post("/productos/<int:id>/eliminar")
@admin_required
def product_delete(id):
    item = Product.query.get_or_404(id)
    public_ids = _public_ids_for_product(item)
    try:
        for public_id in public_ids:
            delete_image(public_id)
        db.session.delete(item)
        db.session.commit()
        flash("Producto eliminado.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.products"))


@admin_bp.post("/productos/<int:id>/imagen/eliminar")
@admin_required
def product_image_delete(id):
    item = Product.query.get_or_404(id)
    old_public_id = item.cloudinary_public_id
    try:
        if old_public_id:
            delete_image(old_public_id)
        item.image = None
        item.cloudinary_public_id = None
        db.session.commit()
        flash("Imagen principal eliminada.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.product_form", id=id))


@admin_bp.post("/productos/<int:id>/imagenes/eliminar/<int:index>")
@admin_required
def product_extra_image_delete(id, index):
    item = Product.query.get_or_404(id)
    urls = item.image_list
    public_ids = item.additional_public_id_list
    if not (0 <= index < len(urls)):
        return redirect(url_for("admin.product_form", id=id))
    public_id = public_ids[index] if index < len(public_ids) else None
    try:
        if public_id:
            delete_image(public_id)
        urls.pop(index)
        if index < len(public_ids):
            public_ids.pop(index)
        item.additional_images = ",".join(urls)
        item.additional_image_public_ids = json.dumps(public_ids)
        db.session.commit()
        flash("Imagen adicional eliminada.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
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
    uploaded = None
    old_public_id = item.cloudinary_public_id
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
        file = request.files.get("image")
        if file and file.filename:
            uploaded = upload_image(file, "mundomix/categories", public_id=f"category-{item.id}-{uuid4().hex}")
            item.image = uploaded["secure_url"]
            item.cloudinary_public_id = uploaded["public_id"]
        db.session.commit()
        if uploaded and old_public_id:
            try:
                delete_image(old_public_id)
            except Exception:
                current_app.logger.exception("Old category image cleanup failed for %s", item.id)
                flash("Categoría guardada, pero no se pudo limpiar la imagen anterior.", "error")
        flash("Categoría actualizada.", "success")
    except Exception as exc:
        db.session.rollback()
        if uploaded:
            _cleanup_uploaded([uploaded])
        flash(str(exc), "error")
    return redirect(url_for("admin.categories"))


@admin_bp.post("/categorias/<int:id>/toggle")
@admin_required
def category_toggle(id):
    item = Category.query.get_or_404(id)
    item.active = not item.active
    db.session.commit()
    flash(f"Categoría {'activada' if item.active else 'desactivada'}.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.post("/categorias/<int:id>/imagen/eliminar")
@admin_required
def category_image_delete(id):
    item = Category.query.get_or_404(id)
    try:
        if item.cloudinary_public_id:
            delete_image(item.cloudinary_public_id)
        item.image = None
        item.cloudinary_public_id = None
        db.session.commit()
        flash("Imagen de categoría eliminada.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.categories"))


@admin_bp.post("/categorias/<int:id>/eliminar")
@admin_required
def category_delete(id):
    item = Category.query.get_or_404(id)
    try:
        if item.cloudinary_public_id:
            delete_image(item.cloudinary_public_id)
        item.image = None
        item.cloudinary_public_id = None
        for product in item.products:
            product.category_id = None
        db.session.delete(item)
        db.session.commit()
        flash("Categoría eliminada; los productos quedaron sin categoría.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/banners", methods=["GET", "POST"])
@admin_required
def banners():
    if request.method == "POST":
        uploaded = None
        try:
            file = request.files.get("image")
            if not file or not file.filename:
                raise ValueError("La imagen del banner es obligatoria.")
            uploaded = upload_image(file, "mundomix/banners", public_id=f"banner-{uuid4().hex}")
            db.session.add(Banner(
                title=request.form.get("title", "").strip(), subtitle=request.form.get("subtitle", "").strip(),
                image=uploaded["secure_url"], cloudinary_public_id=uploaded["public_id"],
                button_text=request.form.get("button_text", "").strip(), button_url=request.form.get("button_url", "").strip(),
                display_order=request.form.get("display_order", 0, type=int), active="active" in request.form,
            ))
            db.session.commit()
            flash("Banner creado.", "success")
        except Exception as exc:
            db.session.rollback()
            if uploaded:
                _cleanup_uploaded([uploaded])
            flash(str(exc), "error")
    return render_template("admin/banners.html", banners=Banner.query.order_by(Banner.display_order, Banner.id).all())


@admin_bp.post("/banners/<int:id>/toggle")
@admin_required
def banner_toggle(id):
    item = Banner.query.get_or_404(id)
    item.active = not item.active
    db.session.commit()
    flash("Banner actualizado.", "success")
    return redirect(url_for("admin.banners"))


@admin_bp.post("/banners/<int:id>/editar")
@admin_required
def banner_edit(id):
    item = Banner.query.get_or_404(id)
    uploaded = None
    old_public_id = item.cloudinary_public_id
    try:
        item.title = request.form.get("title", "").strip()
        item.subtitle = request.form.get("subtitle", "").strip()
        item.button_text = request.form.get("button_text", "").strip()
        item.button_url = request.form.get("button_url", "").strip()
        item.display_order = request.form.get("display_order", 0, type=int)
        item.active = "active" in request.form
        file = request.files.get("image")
        if file and file.filename:
            uploaded = upload_image(file, "mundomix/banners", public_id=f"banner-{item.id}-{uuid4().hex}")
            item.image = uploaded["secure_url"]
            item.cloudinary_public_id = uploaded["public_id"]
        db.session.commit()
        if uploaded and old_public_id:
            try:
                delete_image(old_public_id)
            except Exception:
                current_app.logger.exception("Old banner image cleanup failed for %s", item.id)
                flash("Banner guardado, pero no se pudo limpiar la imagen anterior.", "error")
        flash("Banner actualizado.", "success")
    except Exception as exc:
        db.session.rollback()
        if uploaded:
            _cleanup_uploaded([uploaded])
        flash(str(exc), "error")
    return redirect(url_for("admin.banners"))


@admin_bp.post("/banners/<int:id>/imagen/eliminar")
@admin_required
def banner_image_delete(id):
    item = Banner.query.get_or_404(id)
    try:
        if item.cloudinary_public_id:
            delete_image(item.cloudinary_public_id)
        item.image = None
        item.cloudinary_public_id = None
        db.session.commit()
        flash("Imagen del banner eliminada.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.banners"))


@admin_bp.post("/banners/<int:id>/eliminar")
@admin_required
def banner_delete(id):
    item = Banner.query.get_or_404(id)
    try:
        if item.cloudinary_public_id:
            delete_image(item.cloudinary_public_id)
        db.session.delete(item)
        db.session.commit()
        flash("Banner eliminado.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("admin.banners"))


@admin_bp.get("/pedidos")
@admin_bp.get("/orders")
@admin_required
def orders():
    status = request.args.get("status", "")
    query = Order.query
    if status in STATUSES:
        query = query.filter_by(status=status)
    return render_template("admin/orders.html", orders=query.order_by(desc(Order.created_at)).all(), statuses=STATUSES, selected_status=status)


@admin_bp.route("/pedidos/<int:id>", methods=["GET", "POST"])
@admin_required
def order_detail(id):
    if request.method == "POST":
        order = db.session.execute(select(Order).where(Order.id == id).with_for_update()).scalar_one_or_none()
        if order is None:
            return redirect(url_for("admin.orders"))
        new_status = request.form.get("status")
        if new_status not in STATUSES:
            flash("Estado inválido.", "error")
        elif new_status == "Confirmado" and order.status != "Confirmado":
            product_ids = sorted({oi.product_id for oi in order.items if oi.product_id})
            locked_products = {}
            for product_id in product_ids:
                product = db.session.execute(select(Product).where(Product.id == product_id).with_for_update()).scalar_one_or_none()
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
            order.status = new_status
            db.session.commit()
            flash("Pedido confirmado y stock descontado.", "success")
        elif order.status == "Confirmado" and new_status != "Confirmado":
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


@admin_bp.route("/configuracion", methods=["GET", "POST"])
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    keys = ["store_name", "whatsapp_number", "description", "contact", "social", "instagram", "facebook", "pickup_address", "business_hours", "delivery_info"]
    if request.method == "POST":
        try:
            for key in keys:
                row = Setting.query.filter_by(key=key).first()
                if not row:
                    row = Setting(key=key)
                    db.session.add(row)
                row.value = request.form.get(key, "").strip()
            db.session.commit()
            flash("Configuración guardada.", "success")
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "error")
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/settings.html", settings=settings)
