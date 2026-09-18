from decimal import Decimal, InvalidOperation
from functools import wraps
from uuid import uuid4
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash
from extensions import db
from models.order import Order, OrderItem
from models.restaurant import Restaurant, RestaurantCategory, RestaurantProduct, RestaurantHour, ModifierGroup, ProductModifierGroup, ComboComponent
from routes.restaurant_auth import restaurant_required
from routes.restaurant_common import ARG_TZ, restaurant_is_open
from datetime import datetime, timedelta, timezone
import json
from slugify import make_slug
from services.cloudinary_service import upload_image, delete_image

restaurant_panel_bp = Blueprint("restaurant_panel", __name__)
ALLOWED = {"jpg", "jpeg", "png", "webp"}
STATUSES = ["Nuevo", "Contactado", "Confirmado", "Preparando", "Listo", "En camino", "Entregado", "Cancelado"]


def current_restaurant():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return None
    return db.session.get(Restaurant, restaurant_id)


def money(value):
    try:
        amount = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValueError("Ingresá un precio válido.")
    if amount < 0:
        raise ValueError("El precio no puede ser negativo.")
    return amount


def image_save(file, folder, public_id=None):
    if not file or not file.filename:
        return None
    return upload_image(file, folder, public_id=public_id)


def remove_saved_image(relative_path):
    """Legacy filesystem cleanup only; new images are never stored here."""
    if not relative_path:
        return
    from pathlib import Path
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        current_app.logger.warning("Rejected legacy image deletion outside upload folder: %s", relative_path)
        return
    try:
        if target.is_file(): target.unlink()
    except OSError:
        current_app.logger.exception("Could not delete legacy image: %s", relative_path)


def remove_cloudinary_image(public_id):
    if public_id:
        delete_image(public_id)

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
    restaurant=current_restaurant()
    if restaurant is None:
        session.pop("restaurant_user_id",None); session.pop("restaurant_id",None); return redirect(url_for("restaurant_auth.login"))
    now_local=datetime.now(ARG_TZ); local_start=now_local.replace(hour=0,minute=0,second=0,microsecond=0); local_end=local_start+timedelta(days=1)
    start=local_start.astimezone(timezone.utc).replace(tzinfo=None); end=local_end.astimezone(timezone.utc).replace(tzinfo=None)
    today=Order.query.filter(Order.restaurant_id==restaurant.id,Order.created_at>=start,Order.created_at<end)
    valid_today=today.filter(Order.status!="Cancelado")
    sales=Decimal(str(db.session.query(func.coalesce(func.sum(Order.total),0)).filter(Order.restaurant_id==restaurant.id,Order.status!="Cancelado",Order.created_at>=start,Order.created_at<end).scalar() or 0))
    pending=Order.query.filter(Order.restaurant_id==restaurant.id,Order.status.in_(["Nuevo","Contactado","Confirmado","Preparando","Listo","En camino"])).count()
    active_products=RestaurantProduct.query.filter_by(restaurant_id=restaurant.id,active=True).count(); soldout=RestaurantProduct.query.filter_by(restaurant_id=restaurant.id,active=True,stock_control=True,stock=0).count()
    top=(db.session.query(RestaurantProduct.name,func.coalesce(func.sum(OrderItem.quantity),0).label("qty"))
         .join(OrderItem,OrderItem.restaurant_product_id==RestaurantProduct.id)
         .join(Order,Order.id==OrderItem.order_id)
         .filter(RestaurantProduct.restaurant_id==restaurant.id,Order.status!="Cancelado")
         .group_by(RestaurantProduct.id,RestaurantProduct.name).order_by(desc("qty")).limit(5).all())
    status_counts={st:Order.query.filter_by(restaurant_id=restaurant.id,status=st).count() for st in STATUSES}
    return render_template("restaurant/panel/dashboard.html",restaurant=restaurant,today_orders=valid_today.count(),pending_orders=pending,sales=sales,products=active_products,soldout_products=soldout,recent_orders=Order.query.filter_by(restaurant_id=restaurant.id).order_by(desc(Order.created_at)).limit(8).all(),is_open=restaurant_is_open(restaurant),status_counts=status_counts,top_products=top,ticket_avg=(sales/valid_today.count() if valid_today.count() else Decimal("0")))


@restaurant_panel_bp.get("/comercio/panel/pedidos/nuevos/count")
@restaurant_required
def new_orders_count():
    restaurant = current_restaurant()
    count = Order.query.filter_by(restaurant_id=restaurant.id, status="Nuevo").count()
    return {"count": count}

@restaurant_panel_bp.get("/comercio/panel/pedidos")
@restaurant_required
def orders():
    restaurant = current_restaurant()
    status = request.args.get("status", "")
    period = request.args.get("period", "today")
    query = Order.query.filter_by(restaurant_id=restaurant.id)
    if status in STATUSES: query = query.filter_by(status=status)
    now = datetime.now(ARG_TZ)
    if period == "yesterday":
        start_local = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7":
        start_local = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now + timedelta(days=1)
        end_local = end_local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "30":
        start_local = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now + timedelta(days=1)
        end_local = end_local.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    start = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    query = query.filter(Order.created_at >= start, Order.created_at < end)
    status_counts = {st: Order.query.filter_by(restaurant_id=restaurant.id, status=st).count() for st in STATUSES}
    return render_template("restaurant/panel/orders.html", restaurant=restaurant, orders=query.order_by(desc(Order.created_at)).all(), statuses=STATUSES, selected_status=status, status_counts=status_counts, period=period)


@restaurant_panel_bp.get("/comercio/panel/pedidos/<int:id>/imprimir")
@restaurant_required
def print_order(id):
    restaurant = current_restaurant()
    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    order.printed_at = datetime.utcnow()
    db.session.commit()
    settings = dict(restaurant.print_settings or {})
    width = settings.get("width", "80") if settings.get("width") in ("58", "80", "a4") else "80"
    return render_template("restaurant/panel/order_print.html", restaurant=restaurant, order=order, print_settings=settings, print_width=width)

@restaurant_panel_bp.route("/comercio/panel/pedidos/<int:id>", methods=["GET", "POST"])
@restaurant_required
def order_detail(id):
    restaurant = current_restaurant()
    order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    if request.method == "POST":
        status = request.form.get("status")
        allowed = {
            "Nuevo": {"Contactado", "Confirmado", "Cancelado"},
            "Contactado": {"Confirmado", "Cancelado"},
            "Confirmado": {"Preparando", "Cancelado"},
            "Preparando": {"Listo", "Cancelado"},
            "Listo": {"En camino", "Entregado", "Cancelado"},
            "En camino": {"Entregado", "Cancelado"},
            "Entregado": set(), "Cancelado": set(),
        }
        if status not in STATUSES:
            flash("Estado inválido.", "error")
        elif status != order.status and status not in allowed.get(order.status, set()):
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
                    if not product:
                        db.session.rollback(); flash(f"El producto de {oi.product_name_snapshot} ya no existe.", "error")
                        order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
                        return render_template("restaurant/panel/order_detail.html", restaurant=restaurant, order=order, statuses=STATUSES)
                    if product.stock_control and product.stock < oi.quantity:
                        db.session.rollback(); flash(f"Stock insuficiente para {oi.product_name_snapshot}.", "error")
                        order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
                        return render_template("restaurant/panel/order_detail.html", restaurant=restaurant, order=order, statuses=STATUSES)
                    if product.stock_control:
                        product.stock -= oi.quantity
            order.status = status
            order.stock_deducted = True
            db.session.commit(); flash("Pedido confirmado y stock descontado.", "success")
        else:
            if status == "Confirmado" and order.stock_deducted:
                flash("Este pedido ya tenía el stock descontado; no se vuelve a descontar.", "success")
            order.status = status
            db.session.commit()
            if status != "Confirmado" or not order.stock_deducted:
                flash("Pedido actualizado.", "success")
        order = Order.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    return render_template("restaurant/panel/order_detail.html", restaurant=restaurant, order=order, statuses=STATUSES)


@restaurant_panel_bp.route("/comercio/panel/configuracion", methods=["GET", "POST"])
@restaurant_required
def settings():
    restaurant=current_restaurant()
    if request.method=="POST":
        if request.form.get("quick_status"):
            restaurant.accept_orders = not restaurant.accept_orders
            db.session.commit()
            flash("Estado de pedidos actualizado.", "success")
            return redirect(url_for("restaurant_panel.dashboard"))
        try:
            restaurant.name=request.form.get("name","").strip() or restaurant.name; restaurant.description=request.form.get("description","").strip(); restaurant.food_type=request.form.get("food_type","Comida rápida").strip()
            restaurant.address=request.form.get("address","").strip(); restaurant.phone=request.form.get("phone","").strip(); restaurant.whatsapp=request.form.get("whatsapp","").strip(); restaurant.instagram=request.form.get("instagram","").strip(); restaurant.facebook=request.form.get("facebook","").strip(); restaurant.info=request.form.get("info","").strip()
            restaurant.accept_orders="accept_orders" in request.form; restaurant.accept_orders_closed="accept_orders_closed" in request.form; restaurant.pause_message=request.form.get("pause_message","").strip() or restaurant.pause_message
            restaurant.delivery_enabled="delivery_enabled" in request.form; restaurant.pickup_enabled="pickup_enabled" in request.form; restaurant.delivery_fee=money(request.form.get("delivery_fee","0")); restaurant.minimum_order=money(request.form.get("minimum_order","0"))
            restaurant.prep_min=max(0,request.form.get("prep_min",20,type=int)); restaurant.prep_max=max(restaurant.prep_min,request.form.get("prep_max",30,type=int)); restaurant.theme_color=request.form.get("theme_color","#e21b23").strip() or "#e21b23"
            restaurant.delivery_zones=[{"name":n.strip(),"fee":float(money(f).quantize(Decimal("0.01")))} for n,f in zip(request.form.getlist("zone_name"),request.form.getlist("zone_fee")) if n.strip()]
            restaurant.meta_title=request.form.get("meta_title","").strip(); restaurant.meta_description=request.form.get("meta_description","").strip()
            width=request.form.get("print_width","80")
            if width not in ("58","80","a4"): width="80"
            restaurant.print_settings={
                "width": width,
                "show_mundomix_logo": "show_mundomix_logo" in request.form,
                "show_restaurant_logo": "show_restaurant_logo" in request.form,
                "show_address": "show_address" in request.form,
                "show_phone": "show_phone" in request.form,
            }
            uploaded=[]
            logo=image_save(request.files.get("logo"),f"mundomix/restaurants/{restaurant.id}/logo",public_id=f"restaurant-{restaurant.id}-logo-{uuid4().hex[:8]}")
            if logo: uploaded.append(logo["public_id"])
            banner=image_save(request.files.get("banner"),f"mundomix/restaurants/{restaurant.id}/banner",public_id=f"restaurant-{restaurant.id}-banner-{uuid4().hex[:8]}")
            if banner: uploaded.append(banner["public_id"])
            old_logo,old_banner=restaurant.logo,restaurant.banner
            old_logo_id,old_banner_id=restaurant.logo_cloudinary_public_id,restaurant.banner_cloudinary_public_id
            if logo: restaurant.logo_url=logo["secure_url"]; restaurant.logo_cloudinary_public_id=logo["public_id"]
            if banner: restaurant.banner_url=banner["secure_url"]; restaurant.banner_cloudinary_public_id=banner["public_id"]
            for day in range(7):
                hour=RestaurantHour.query.filter_by(restaurant_id=restaurant.id,weekday=day).first() or RestaurantHour(restaurant_id=restaurant.id,weekday=day); db.session.add(hour)
                hour.closed=f"closed_{day}" in request.form; hour.start_time=request.form.get(f"start_{day}","19:00"); hour.end_time=request.form.get(f"end_{day}","00:00"); hour.start_time_2=request.form.get(f"start2_{day}",""); hour.end_time_2=request.form.get(f"end2_{day}","")
            db.session.commit()
            if logo and old_logo_id:
                try: remove_cloudinary_image(old_logo_id)
                except Exception: current_app.logger.exception("Could not delete replaced restaurant logo %s", old_logo_id)
            if banner and old_banner_id:
                try: remove_cloudinary_image(old_banner_id)
                except Exception: current_app.logger.exception("Could not delete replaced restaurant banner %s", old_banner_id)
            if logo and old_logo: remove_saved_image(old_logo)
            if banner and old_banner: remove_saved_image(old_banner)
            flash("Configuración guardada.","success")
        except ValueError as exc:
            db.session.rollback()
            for public_id in locals().get("uploaded", []):
                try: remove_cloudinary_image(public_id)
                except Exception: current_app.logger.exception("Cloudinary cleanup failed for %s", public_id)
            flash(str(exc),"error")
        except SQLAlchemyError:
            db.session.rollback()
            for public_id in locals().get("uploaded", []):
                try: remove_cloudinary_image(public_id)
                except Exception: current_app.logger.exception("Cloudinary cleanup failed for %s", public_id)
            current_app.logger.exception("Restaurant settings database error"); flash("No pudimos guardar la configuración.","error")
    return render_template("restaurant/panel/settings.html",restaurant=restaurant)


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
    restaurant=current_restaurant(); item=RestaurantProduct.query.filter_by(id=id,restaurant_id=restaurant.id).first() if id else None
    if id and not item:return redirect(url_for("restaurant_panel.products"))
    categories=RestaurantCategory.query.filter_by(restaurant_id=restaurant.id).order_by(RestaurantCategory.display_order,RestaurantCategory.name).all(); groups=ModifierGroup.query.filter_by(restaurant_id=restaurant.id).order_by(ModifierGroup.display_order,ModifierGroup.name).all(); components=RestaurantProduct.query.filter(RestaurantProduct.restaurant_id==restaurant.id,RestaurantProduct.id!=(id or -1)).order_by(RestaurantProduct.name).all()
    if request.method=="POST":
        try:
            name=request.form.get("name","").strip()
            if not name:raise ValueError("El nombre es obligatorio.")
            if not item:
                item=RestaurantProduct(restaurant_id=restaurant.id,name=name,slug="temp",sku=unique_sku(restaurant.id,request.form.get("sku","").strip()),price_delivery=0,price_pickup=0); db.session.add(item); db.session.flush()
            else:item.sku=unique_sku(restaurant.id,request.form.get("sku","").strip(),item.id)
            item.name=name; item.slug=unique_product_slug(restaurant.id,name,item.id); item.description=request.form.get("description","").strip(); item.price_delivery=money(request.form.get("price_delivery","0")); item.price_pickup=money(request.form.get("price_pickup","0")); item.previous_price=money(request.form.get("previous_price","0")) if request.form.get("previous_price") else None; item.stock=max(0,request.form.get("stock",0,type=int)); item.stock_control="stock_control" in request.form
            category_id=request.form.get("category_id",type=int) or None
            if category_id and not RestaurantCategory.query.filter_by(id=category_id,restaurant_id=restaurant.id).first():raise ValueError("La categoría seleccionada no pertenece a este local.")
            item.category_id=category_id; item.featured="featured" in request.form; item.active="active" in request.form; item.display_order=request.form.get("display_order",0,type=int); item.label=request.form.get("label","").strip()[:40]; item.nutrition=request.form.get("nutrition","").strip(); item.prep_min=request.form.get("prep_min",type=int) or None; item.prep_max=request.form.get("prep_max",type=int) or None; item.is_combo="is_combo" in request.form
            uploaded=[]
            image=image_save(request.files.get("image"),f"mundomix/restaurants/{restaurant.id}/products",public_id=f"restaurant-{restaurant.id}-product-{item.id}-{uuid4().hex[:8]}")
            if image: uploaded.append(image["public_id"])
            old_image=item.image; old_image_id=item.cloudinary_public_id
            if image: item.image_url=image["secure_url"]; item.cloudinary_public_id=image["public_id"]
            # Rebuild only this product's modifier associations, all tenant-scoped.
            ProductModifierGroup.query.filter_by(product_id=item.id).delete(synchronize_session=False)
            for gid in request.form.getlist("modifier_group_ids",type=int):
                g=ModifierGroup.query.filter_by(id=gid,restaurant_id=restaurant.id).first()
                if g:db.session.add(ProductModifierGroup(product_id=item.id,group_id=g.id,display_order=g.display_order))
            ComboComponent.query.filter_by(combo_id=item.id).delete(synchronize_session=False)
            if item.is_combo:
                for pid in request.form.getlist("component_product_ids",type=int):
                    if pid==item.id:continue
                    c=RestaurantProduct.query.filter_by(id=pid,restaurant_id=restaurant.id).first()
                    if c:db.session.add(ComboComponent(combo_id=item.id,product_id=c.id,quantity=max(1,request.form.get(f"component_qty_{pid}",1,type=int))))
            db.session.commit();
            if image and old_image_id:
                try: remove_cloudinary_image(old_image_id)
                except Exception: current_app.logger.exception("Could not delete replaced restaurant product image %s", old_image_id)
            flash("Producto guardado.","success"); return redirect(url_for("restaurant_panel.products"))
        except ValueError as exc:
            db.session.rollback()
            for public_id in locals().get("uploaded", []):
                try: remove_cloudinary_image(public_id)
                except Exception: current_app.logger.exception("Cloudinary cleanup failed for %s", public_id)
            flash(str(exc),"error")
        except (IntegrityError,SQLAlchemyError):
            db.session.rollback()
            for public_id in locals().get("uploaded", []):
                try: remove_cloudinary_image(public_id)
                except Exception: current_app.logger.exception("Cloudinary cleanup failed for %s", public_id)
            current_app.logger.exception("Restaurant product database error");flash("No pudimos guardar el producto. Revisá los datos.","error")
    selected_groups={x.group_id for x in item.modifier_links} if item else set(); selected_components={x.product_id:x.quantity for x in item.combo_components} if item else {}
    return render_template("restaurant/panel/product_form.html",restaurant=restaurant,product=item,categories=categories,groups=groups,selected_groups=selected_groups,components=components,selected_components=selected_components)


@restaurant_panel_bp.post("/comercio/panel/productos/<int:id>/toggle")
@restaurant_required
def product_toggle(id):
    restaurant = current_restaurant(); item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404(); item.active = not item.active; db.session.commit(); return redirect(url_for("restaurant_panel.products"))


@restaurant_panel_bp.post("/comercio/panel/configuracion/logo/eliminar")
@restaurant_required
def logo_delete():
    restaurant = current_restaurant()
    old = restaurant.logo; old_id = restaurant.logo_cloudinary_public_id
    if old_id: remove_cloudinary_image(old_id)
    restaurant.logo_url = None; restaurant.logo_cloudinary_public_id = None; restaurant.logo = None
    db.session.commit()
    remove_saved_image(old)
    flash("Logo eliminado.", "success")
    return redirect(url_for("restaurant_panel.settings"))


@restaurant_panel_bp.post("/comercio/panel/configuracion/banner/eliminar")
@restaurant_required
def banner_delete():
    restaurant = current_restaurant()
    old = restaurant.banner; old_id = restaurant.banner_cloudinary_public_id
    if old_id: remove_cloudinary_image(old_id)
    restaurant.banner_url = None; restaurant.banner_cloudinary_public_id = None; restaurant.banner = None
    db.session.commit()
    remove_saved_image(old)
    flash("Banner eliminado.", "success")
    return redirect(url_for("restaurant_panel.settings"))


@restaurant_panel_bp.post("/comercio/panel/productos/<int:id>/imagen/eliminar")
@restaurant_required
def product_image_delete(id):
    restaurant = current_restaurant()
    item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    old = item.image; old_id = item.cloudinary_public_id
    if old_id: remove_cloudinary_image(old_id)
    item.image_url = None; item.cloudinary_public_id = None; item.image = None
    db.session.commit()
    remove_saved_image(old)
    flash("Imagen eliminada.", "success")
    return redirect(url_for("restaurant_panel.product_form", id=id))


@restaurant_panel_bp.post("/comercio/panel/productos/<int:id>/eliminar")
@restaurant_required
def product_delete(id):
    restaurant = current_restaurant(); item = RestaurantProduct.query.filter_by(id=id, restaurant_id=restaurant.id).first_or_404()
    if item.order_items or item.combo_components:
        item.active = False; flash("El producto tiene historial o forma parte de un combo y fue desactivado en lugar de eliminarse.", "success")
    else:
        old_id=item.cloudinary_public_id
        if old_id: remove_cloudinary_image(old_id)
        db.session.delete(item); flash("Producto eliminado.", "success")
    db.session.commit(); return redirect(url_for("restaurant_panel.products"))

@restaurant_panel_bp.get("/comercio/panel/estadisticas")
@restaurant_required
def statistics():
    restaurant=current_restaurant(); period=request.args.get("period","7")
    days=30 if period=="30" else (1 if period=="1" else 7)
    now=datetime.now(ARG_TZ); local_start=(now-timedelta(days=days-1)).replace(hour=0,minute=0,second=0,microsecond=0); start=local_start.astimezone(timezone.utc).replace(tzinfo=None)
    valid=Order.query.filter(Order.restaurant_id==restaurant.id,Order.status!="Cancelado",Order.created_at>=start)
    orders_count=valid.count(); sales=Decimal(str(db.session.query(func.coalesce(func.sum(Order.total),0)).filter(Order.restaurant_id==restaurant.id,Order.status!="Cancelado",Order.created_at>=start).scalar() or 0))
    top=(db.session.query(RestaurantProduct.name,func.sum(OrderItem.quantity).label("qty")).join(OrderItem,OrderItem.restaurant_product_id==RestaurantProduct.id).join(Order,Order.id==OrderItem.order_id).filter(RestaurantProduct.restaurant_id==restaurant.id,Order.status!="Cancelado",Order.created_at>=start).group_by(RestaurantProduct.id,RestaurantProduct.name).order_by(desc("qty")).limit(10).all())
    return render_template("restaurant/panel/statistics.html",restaurant=restaurant,period=period,days=days,orders_count=orders_count,sales=sales,ticket_avg=(sales/orders_count if orders_count else Decimal("0")),top_products=top)
