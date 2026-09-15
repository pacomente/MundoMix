from decimal import Decimal
import secrets
from urllib.parse import quote

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db
from models.order import Order, OrderItem
from models.product import Product
from models.settings import Setting

checkout_bp = Blueprint("checkout", __name__)


def _normalise_method(value):
    return value if value in ("delivery", "pickup") else "delivery"


def build_items(method):
    method = _normalise_method(method)
    cart = session.get("cart") or {}
    items = []
    total = Decimal("0.00")
    for sid, raw_qty in list(cart.items()):
        try:
            product_id, qty = int(sid), int(raw_qty)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        product = db.session.get(Product, product_id)
        if not product or not product.active or product.stock <= 0:
            continue
        if qty > product.stock:
            raise ValueError(f"No hay stock suficiente de {product.name}. Quedan {product.stock} unidades.")
        price = Decimal(str(product.price_delivery if method == "delivery" else product.price_pickup))
        subtotal = price * qty
        items.append((product, qty, price, subtotal))
        total += subtotal
    return items, total


def whatsapp_number():
    setting = Setting.query.filter_by(key="whatsapp_number").first()
    return (setting.value if setting else "") or current_app.config.get("WHATSAPP_NUMBER", "")


def _order_whatsapp_url(order):
    number = "".join(ch for ch in whatsapp_number() if ch.isdigit())
    if not number:
        return None
    lines = [
        "MundoMix — Nuevo pedido", f"Pedido #{order.id:04d}", "",
        f"Cliente: {order.customer_name}", f"Teléfono: {order.customer_phone}",
        f"Método: {'Envío' if order.fulfillment_method == 'delivery' else 'Retiro en local'}",
    ]
    if order.fulfillment_method == "delivery":
        lines.append(f"Dirección: {order.address}")
    lines += ["", "Productos:"]
    for item in order.items:
        lines.append(f"{item.product_name_snapshot} x{item.quantity} — ${item.subtotal:,.0f}")
    lines += ["", f"Total: ${order.total:,.0f}", f"Notas: {order.notes or 'Sin notas'}"]
    return f"https://wa.me/{number}?text={quote(chr(10).join(lines))}"


def render_checkout(method, message=None):
    method = _normalise_method(method)
    try:
        items, total = build_items(method)
    except ValueError as exc:
        flash(str(exc), "error")
        items, total = [], Decimal("0.00")
    except SQLAlchemyError:
        current_app.logger.exception("Could not rebuild checkout cart")
        items, total = [], Decimal("0.00")
        message = message or "No pudimos cargar tu carrito en este momento. Intentá nuevamente."
    if message:
        flash(message, "error")
    return render_template("store/checkout.html", items=items, total=total, method=method)


@checkout_bp.route("/", methods=["GET", "POST"])
def checkout():
    if not session.get("cart"):
        flash("Tu carrito está vacío.", "error")
        return redirect(url_for("cart.view"))
    method = _normalise_method(session.get("fulfillment_method", "delivery"))

    if request.method == "GET":
        session["checkout_form_token"] = secrets.token_urlsafe(24)
        return render_checkout(method)

    token = request.form.get("checkout_token", "").strip()
    if not token or token != session.get("checkout_form_token"):
        return render_checkout(method, "Este formulario venció. Actualizá la página e intentá nuevamente.")

    name = request.form.get("customer_name", "").strip()
    phone = request.form.get("customer_phone", "").strip()
    address = request.form.get("address", "").strip()
    notes = request.form.get("notes", "").strip()
    method = _normalise_method(request.form.get("fulfillment_method", method))
    if not name or not phone:
        return render_checkout(method, "Completá nombre y teléfono/WhatsApp.")
    if method == "delivery" and not address:
        return render_checkout(method, "La dirección es obligatoria para envíos.")

    try:
        items, total = build_items(method)
        if not items:
            return render_checkout(method, "No hay productos disponibles en tu carrito.")
        order = Order(
            customer_name=name, customer_phone=phone, fulfillment_method=method,
            address=address if method == "delivery" else "", notes=notes,
            total=total, status="Nuevo", checkout_token=token,
        )
        db.session.add(order)
        db.session.flush()
        for product, qty, price, subtotal in items:
            db.session.add(OrderItem(order_id=order.id, product_id=product.id,
                                     product_name_snapshot=product.name, quantity=qty,
                                     unit_price=price, subtotal=subtotal))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.info("Duplicate checkout token rejected: %s", token)
        existing = Order.query.filter_by(checkout_token=token, restaurant_id=None).first()
        if existing:
            session["cart"] = {}
            session.pop("checkout_form_token", None)
            session["last_checkout_token"] = token
            session.modified = True
            existing_url = _order_whatsapp_url(existing)
            if existing_url:
                return redirect(existing_url)
        return render_checkout(method, "Este pedido ya fue enviado. Revisá la pantalla anterior antes de volver a intentarlo.")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Checkout PostgreSQL/SQLAlchemy error")
        return render_checkout(method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unexpected MundoMix checkout error")
        return render_checkout(method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")

    whatsapp_url = _order_whatsapp_url(order)
    session["cart"] = {}
    session.pop("checkout_form_token", None)
    session["last_checkout_token"] = token
    session["fulfillment_method"] = method
    session.modified = True
    if whatsapp_url:
        return redirect(whatsapp_url)
    return render_template("store/order_success.html", order=order, whatsapp_url="")
