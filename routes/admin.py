from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash

from extensions import db
from models import Admin, Banner, Category, Order, OrderItem, Product, Setting
from services.cloudinary_service import delete_image, upload_image
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


def safe_next(value):
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def parse_money(value):
    try:
        amount = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValueError("Ingresá un precio válido.")
    if amount < 0:
        raise ValueError("Los precios no pueden ser negativos.")
    return amount


def unique_slug(name, current_id=None):
    base = make_slug(name) or "producto"
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


def unique_category_slug(name, current_id=None):
    base = make_slug(name) or "categoria"
    slug = base
    i = 2
    while True:
        query = Category.query.filter_by(slug=slug)
        if current_id:
            query = query.filter(Category.id != current_id)
        if not query.first():
            return slug
        slug = f"{base}-{i}"
        i += 1


def _upload_many(files, folder):
    uploaded = []
    for file in files:
        if file and file.filename:
            uploaded.append(upload_image(file, folder))
    return uploaded


def _cleanup_assets(assets):
    for asset in assets:
        try:
            delete_image(asset.get("public_id"))
        except Exception:
            current_app.logger.exception("Could not clean up Cloudinary asset %s", asset.get("public_id"))


def _delete_asset_or_keep_reference(public_id):
    """Delete a Cloudinary asset and only let the caller clear DB afterwards."""
    if not public_id:
        return
    delete_image(public_id)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.clear()
            session["admin_id"] = admin.id
            return redirect(safe_next(request.args.get("next")) or url_for("admin.dashboard"))
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
    best = (
        db.session.query(OrderItem.product_name_snapshot, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status != "Cancelado")
        .group_by(OrderItem.product_name_snapshot)
        .order_by(desc("qty"))
        .limit(5)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        total_products=Product.query.count(),
        active_products=Product.query.filter_by(active=True).count(),
        out_stock=Product.query.filter(Product.stock <= 0).count(),
        featured_products=Product.query.filter_by(featured=True, active=True).count(),
        total_orders=Order.query.count(),
        new_orders=Order.query.filter_by(status="Nuevo").count(),
        confirmed_orders=Order.query.filter_by(status="Confirmado").count(),
        delivered_orders=Order.query.filter_by(status="Entregado").count(),
        sales=Decimal(str(sales)),
        recent_orders=Order.query.order_by(desc(Order.created_at)).limit(8).all(),
        best_products=best,
    )


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
        new_assets = []
        old_main_id = item.cloudinary_public_id if item else None
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

            image_file = request.files.get("image")
            if image_file and image_file.filename:
                asset = upload_image(image_file, "products")
                new_assets.append(asset)
                item.image = asset["secure_url"]
                item.cloudinary_public_id = asset["public_id"]

            extra_assets = _upload_many(request.files.getlist("additional_images"), "products")
            new_assets.extend(extra_assets)
            if extra_assets:
                existing = item.additional_image_assets
                existing.extend(extra_assets)
                item.set_additional_image_assets(existing)

            db.session.commit()
        except (ValueError, SQLAlchemyError) as exc:
            db.session.rollback()
            _cleanup_assets(new_assets)
            current_app.logger.exception("Could not save product")
            flash(str(exc), "error")
            return render_template("admin/product_form.html", product=item, categories=categories)
        except Exception as exc:
            db.session.rollback()
            _cleanup_assets(new_assets)
            current_app.logger.exception("Unexpected product save error")
            flash("No se pudo guardar el producto. Revisá el formulario y los logs.", "error")
            return render_template("admin/product_form.html", product=item, categories=categories)

        # Old assets are removed only after the DB points to the new asset.
        if old_main_id and old_main_id != item.cloudinary_public_id:
            try:
                delete_image(old_main_id)
            except Exception:
                current_app.logger.exception("Could not delete replaced product image %s", old_main_id)
                flash("Producto guardado, pero la imagen anterior quedó pendiente de limpieza en Cloudinary.", "error")
        flash("Producto guardado correctamente.", "success")
        return redirect(url_for("admin.products"))

    return render_template("admin/product_form.html", product=item, categories=categories)


@admin_bp.post("/productos/<int:id>/eliminar")
@admin_required
def product_delete(id):
    item = Product.query.get_or_404(id)
    assets = []
    if item.cloudinary_public_id:
        assets.append(item.cloudinary_public_id)
    assets.extend(a.get("public_id") for a in item.additional_image_assets if a.get("public_id"))
    try:
        for public_id in assets:
            delete_image(public_id)
        db.session.delete(item)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Could not delete product %s", id)
        flash("No se pudo eliminar el producto porque una imagen de Cloudinary no pudo eliminarse.", "error")
        return redirect(url_for("admin.products"))
    flash("Producto eliminado.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.post("/productos/<int:id>/imagen/eliminar")
@admin_required
def product_image_delete(id):
    item = Product.query.get_or_404(id)
    public_id = item.cloudinary_public_id
    try:
        if public_id:
            delete_image(public_id)
        item.image = None
        item.cloudinary_public_id = None
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not delete main product image %s", id)
        flash("No se pudo eliminar la imagen de Cloudinary.", "error")
        return redirect(url_for("admin.product_form", id=id))
    flash("Imagen principal eliminada.", "success")
    return redirect(url_for("admin.product_form", id=id))


@admin_bp.post("/productos/<int:id>/imagenes/eliminar/<int:index>")
@admin_required
def product_extra_image_delete(id, index):
    item = Product.query.get_or_404(id)
    assets = item.additional_image_assets
    if not 0 <= index < len(assets):
        flash("Imagen adicional no encontrada.", "error")
        return redirect(url_for("admin.product_form", id=id))
    asset = assets[index]
    try:
        if asset.get("public_id"):
            delete_image(asset["public_id"])
        assets.pop(index)
        item.set_additional_image_assets(assets)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not delete additional product image %s[%s]", id, index)
        flash("No se pudo eliminar la imagen adicional de Cloudinary.", "error")
        return redirect(url_for("admin.product_form", id=id))
    flash("Imagen adicional eliminada.", "success")
    return redirect(url_for("admin.product_form", id=id))


@admin_bp.post("/productos/<int:id>/toggle")
@admin_required
def product_toggle(id):
    item = Product.query.get_or_404(id)
    try:
        item.active = not item.active
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not toggle product %s", id)
        flash("No se pudo actualizar el producto.", "error")
        return redirect(url_for("admin.products"))
    flash(f"Producto {'activado' if item.active else 'desactivado'}.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/categorias", methods=["GET", "POST"])
@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        new_assets = []
        try:
            name = request.form.get("name", "").strip()
            if not name:
                raise ValueError("El nombre es obligatorio.")
            if Category.query.filter_by(name=name).first():
                raise ValueError("La categoría ya existe.")
            image = request.files.get("image")
            asset = upload_image(image, "categories") if image and image.filename else None
            if asset:
                new_assets.append(asset)
            category = Category(
                name=name,
                slug=unique_category_slug(name),
                description=request.form.get("description", "").strip(),
                image=asset["secure_url"] if asset else None,
                cloudinary_public_id=asset["public_id"] if asset else None,
                active=True,
            )
            db.session.add(category)
            db.session.commit()
            flash("Categoría creada.", "success")
        except Exception as exc:
            db.session.rollback()
            _cleanup_assets(new_assets)
            current_app.logger.exception("Could not create category")
            flash(str(exc), "error")
    return render_template("admin/categories.html", categories=Category.query.order_by(Category.name).all())


@admin_bp.post("/categorias/<int:id>/editar")
@admin_required
def category_edit(id):
    item = Category.query.get_or_404(id)
    old_public_id = item.cloudinary_public_id
    new_asset = None
    try:
        name = request.form.get("name", item.name).strip()
        if not name:
            raise ValueError("El nombre es obligatorio.")
        duplicate = Category.query.filter(Category.name == name, Category.id != item.id).first()
        if duplicate:
            raise ValueError("Ya existe otra categoría con ese nombre.")
        item.name = name
        item.description = request.form.get("description", "").strip()
        item.slug = unique_category_slug(name, item.id)
        image = request.files.get("image")
        if image and image.filename:
            new_asset = upload_image(image, "categories")
            item.image = new_asset["secure_url"]
            item.cloudinary_public_id = new_asset["public_id"]
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if new_asset:
            _cleanup_assets([new_asset])
        current_app.logger.exception("Could not edit category %s", id)
        flash(str(exc), "error")
        return redirect(url_for("admin.categories"))

    if old_public_id and old_public_id != item.cloudinary_public_id:
        try:
            delete_image(old_public_id)
        except Exception:
            current_app.logger.exception("Could not delete replaced category image %s", old_public_id)
            flash("Categoría actualizada, pero la imagen anterior quedó pendiente de limpieza.", "error")
    flash("Categoría actualizada.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.post("/categorias/<int:id>/toggle")
@admin_required
def category_toggle(id):
    item = Category.query.get_or_404(id)
    try:
        item.active = not item.active
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not toggle category %s", id)
        flash("No se pudo actualizar la categoría.", "error")
        return redirect(url_for("admin.categories"))
    flash(f"Categoría {'activada' if item.active else 'desactivada'}.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.post("/categorias/<int:id>/eliminar")
@admin_required
def category_delete(id):
    item = Category.query.get_or_404(id)
    public_id = item.cloudinary_public_id
    try:
        if public_id:
            delete_image(public_id)
        for product in item.products:
            product.category_id = None
        db.session.delete(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not delete category %s", id)
        flash("No se pudo eliminar la categoría porque su imagen no pudo eliminarse.", "error")
        return redirect(url_for("admin.categories"))
    flash("Categoría eliminada; los productos quedaron sin categoría.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/banners", methods=["GET", "POST"])
@admin_required
def banners():
    if request.method == "POST":
        new_asset = None
        try:
            image = request.files.get("image")
            if not image or not image.filename:
                raise ValueError("La imagen del banner es obligatoria.")
            new_asset = upload_image(image, "banners")
            db.session.add(
                Banner(
                    title=request.form.get("title", "").strip(),
                    subtitle=request.form.get("subtitle", "").strip(),
                    image=new_asset["secure_url"],
                    cloudinary_public_id=new_asset["public_id"],
                    button_text=request.form.get("button_text", "").strip(),
                    button_url=request.form.get("button_url", "").strip(),
                    display_order=request.form.get("display_order", 0, type=int),
                    active="active" in request.form,
                )
            )
            db.session.commit()
            flash("Banner creado.", "success")
        except Exception as exc:
            db.session.rollback()
            if new_asset:
                _cleanup_assets([new_asset])
            current_app.logger.exception("Could not create banner")
            flash(str(exc), "error")
    return render_template("admin/banners.html", banners=Banner.query.order_by(Banner.display_order, Banner.id).all())


@admin_bp.post("/banners/<int:id>/toggle")
@admin_required
def banner_toggle(id):
    item = Banner.query.get_or_404(id)
    try:
        item.active = not item.active
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not toggle banner %s", id)
        flash("No se pudo actualizar el banner.", "error")
        return redirect(url_for("admin.banners"))
    flash("Banner actualizado.", "success")
    return redirect(url_for("admin.banners"))


@admin_bp.post("/banners/<int:id>/editar")
@admin_required
def banner_edit(id):
    item = Banner.query.get_or_404(id)
    old_public_id = item.cloudinary_public_id
    new_asset = None
    try:
        item.title = request.form.get("title", "").strip()
        item.subtitle = request.form.get("subtitle", "").strip()
        item.button_text = request.form.get("button_text", "").strip()
        item.button_url = request.form.get("button_url", "").strip()
        item.display_order = request.form.get("display_order", 0, type=int)
        item.active = "active" in request.form
        image = request.files.get("image")
        if image and image.filename:
            new_asset = upload_image(image, "banners")
            item.image = new_asset["secure_url"]
            item.cloudinary_public_id = new_asset["public_id"]
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if new_asset:
            _cleanup_assets([new_asset])
        current_app.logger.exception("Could not edit banner %s", id)
        flash(str(exc), "error")
        return redirect(url_for("admin.banners"))

    if old_public_id and old_public_id != item.cloudinary_public_id:
        try:
            delete_image(old_public_id)
        except Exception:
            current_app.logger.exception("Could not delete replaced banner image %s", old_public_id)
            flash("Banner actualizado, pero la imagen anterior quedó pendiente de limpieza.", "error")
    flash("Banner actualizado.", "success")
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
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not delete banner %s", id)
        flash("No se pudo eliminar el banner porque su imagen no pudo eliminarse.", "error")
        return redirect(url_for("admin.banners"))
    flash("Banner eliminado.", "success")
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
    try:
        if request.method == "POST":
            order = db.session.execute(select(Order).where(Order.id == id).with_for_update()).scalar_one_or_none()
            if order is None:
                return redirect(url_for("admin.orders"))
            new_status = request.form.get("status")
            if new_status not in STATUSES:
                raise ValueError("Estado inválido.")
            if new_status == "Confirmado" and not order.stock_deducted:
                product_ids = sorted({oi.product_id for oi in order.items if oi.product_id})
                locked_products = {}
                for product_id in product_ids:
                    product = db.session.execute(select(Product).where(Product.id == product_id).with_for_update()).scalar_one_or_none()
                    locked_products[product_id] = product
                for oi in order.items:
                    if oi.product_id:
                        product = locked_products.get(oi.product_id)
                        if not product or product.stock < oi.quantity:
                            raise ValueError(f"Stock insuficiente para {oi.product_name_snapshot}.")
                        product.stock -= oi.quantity
                order.stock_deducted = True
                order.status = new_status
                db.session.commit()
                flash("Pedido confirmado y stock descontado.", "success")
            else:
                order.status = new_status
                db.session.commit()
                flash("Pedido actualizado.", "success")
        else:
            order = Order.query.get_or_404(id)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        order = Order.query.get_or_404(id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not update order %s", id)
        flash("No se pudo actualizar el pedido.", "error")
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
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Could not save settings")
            flash("No se pudo guardar la configuración.", "error")
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/settings.html", settings=settings)
