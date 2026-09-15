from decimal import Decimal
import secrets
from urllib.parse import quote

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db
from models.order import Order, OrderItem
from models.restaurant import Restaurant
from routes.restaurant_cart import get_restaurant_cart
from routes.restaurant_common import restaurant_is_open

restaurant_checkout_bp = Blueprint("restaurant_checkout", __name__)


def _whatsapp_number(restaurant):
    """Normalize a configured Argentine WhatsApp number for wa.me.

    We strip formatting and normalize common +54 / 00 54 forms. We do not
    guess an area code or transform an unknown local number into a different
    subscriber number.
    """
    raw = "".join(ch for ch in (restaurant.whatsapp or "") if ch.isdigit())
    if raw.startswith("00"):
        raw = raw[2:]
    if raw.startswith("54"):
        rest = raw[2:]
        if rest.startswith("0"):
            rest = rest[1:]
        if not rest:
            return ""
        return "54" + rest
    if raw.startswith("0"):
        raw = raw[1:]
    # Common Argentine local mobile form: area code + subscriber, without +54.
    # Add the mobile country-code prefix without guessing an area code.
    if len(raw) == 10:
        return "549" + raw
    return raw


def _order_whatsapp_url(order):
    restaurant = order.restaurant
    number = _whatsapp_number(restaurant)
    if not number:
        return None
    lines = [
        f"Hola {restaurant.name} 👋", "", "Quiero realizar el siguiente pedido:", "",
        f"Pedido #{order.id:04d}", "", f"Cliente: {order.customer_name}",
        f"Teléfono: {order.customer_phone}",
        f"Modalidad: {'Delivery' if order.fulfillment_method == 'delivery' else 'Retiro'}",
    ]
    if order.fulfillment_method == "delivery":
        lines.append(f"Dirección: {order.address}")
    lines += ["", "Pedido:"]
    for item in order.items:
        lines.append(f"{item.quantity}x {item.product_name_snapshot} — ${item.subtotal:,.0f}")
    lines += ["", f"TOTAL: ${order.total:,.0f}", "", f"Notas: {order.notes or 'Sin notas'}"]
    return f"https://wa.me/{number}?text={quote(chr(10).join(lines))}"


def _render(restaurant, method, error=None):
    try:
        items, total = get_restaurant_cart(restaurant.id, method)
    except SQLAlchemyError:
        current_app.logger.exception("Could not rebuild restaurant checkout cart")
        items, total = [], Decimal("0.00")
        error = error or "No pudimos cargar tu carrito en este momento. Intentá nuevamente."
    if error:
        flash(error, "error")
    return render_template(
        "restaurant/checkout.html", restaurant=restaurant, items=items,
        total=total, method=method, is_open=restaurant_is_open(restaurant)
    )


@restaurant_checkout_bp.route("/comida/<slug>/checkout", methods=["GET", "POST"])
def checkout(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    method = session.get("restaurant_fulfillment_method", "delivery")
    if method not in ("delivery", "pickup"):
        method = "delivery"

    if request.method == "GET":
        session["restaurant_checkout_form_token"] = secrets.token_urlsafe(24)
        items, _ = get_restaurant_cart(restaurant.id, method)
        if not items:
            flash("Tu carrito está vacío.", "error")
            return redirect(url_for("restaurant_cart.view", slug=slug))
        return _render(restaurant, method)

    token = request.form.get("checkout_token", "").strip()
    if not token or token != session.get("restaurant_checkout_form_token"):
        return _render(restaurant, method, "Este formulario venció. Actualizá la página e intentá nuevamente.")

    method = request.form.get("fulfillment_method", method)
    if method not in ("delivery", "pickup"):
        method = "delivery"
    name = request.form.get("customer_name", "").strip()
    phone = request.form.get("customer_phone", "").strip()
    address = request.form.get("address", "").strip()
    notes = request.form.get("notes", "").strip()

    if not name or not phone:
        return _render(restaurant, method, "Completá nombre y teléfono/WhatsApp.")
    if method == "delivery" and not address:
        return _render(restaurant, method, "La dirección es obligatoria para envíos.")
    if not _whatsapp_number(restaurant):
        return _render(restaurant, method, "Este local todavía no configuró su WhatsApp. Contactá al administrador.")
    if not restaurant_is_open(restaurant) and not restaurant.accept_orders_closed:
        return _render(restaurant, method, "El local está cerrado y no está aceptando pedidos en este momento.")

    try:
        items, total = get_restaurant_cart(restaurant.id, method)
        if not items:
            return _render(restaurant, method, "No hay productos disponibles en tu carrito.")
        order = Order(
            restaurant_id=restaurant.id, customer_name=name, customer_phone=phone,
            fulfillment_method=method, address=address if method == "delivery" else "",
            notes=notes, total=total, status="Nuevo", checkout_token=token,
        )
        db.session.add(order)
        db.session.flush()
        for item in items:
            product = item["product"]
            db.session.add(OrderItem(
                order_id=order.id, restaurant_product_id=product.id,
                product_name_snapshot=product.name, quantity=item["quantity"],
                unit_price=item["unit_price"], subtotal=item["subtotal"],
            ))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.info("Duplicate restaurant checkout token rejected: %s", token)
        existing = Order.query.filter_by(checkout_token=token, restaurant_id=restaurant.id).first()
        if existing:
            session.setdefault("restaurant_cart", {}).pop(str(restaurant.id), None)
            session.pop("restaurant_checkout_form_token", None)
            session["restaurant_last_checkout_token"] = token
            session.modified = True
            existing_url = _order_whatsapp_url(existing)
            if existing_url:
                return redirect(existing_url)
        return _render(restaurant, method, "Este pedido ya fue enviado. Revisá WhatsApp antes de intentarlo nuevamente.")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Restaurant checkout database error")
        return _render(restaurant, method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unexpected restaurant checkout error")
        return _render(restaurant, method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")

    whatsapp_url = _order_whatsapp_url(order)
    if not whatsapp_url:
        return _render(restaurant, method, "Este local no tiene un WhatsApp válido configurado.")

    session.setdefault("restaurant_cart", {}).pop(str(restaurant.id), None)
    session.pop("restaurant_checkout_form_token", None)
    session["restaurant_last_checkout_token"] = token
    session.modified = True
    return redirect(whatsapp_url)
