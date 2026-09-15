from decimal import Decimal
import secrets
from urllib.parse import quote
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models.order import Order, OrderItem
from models.restaurant import Restaurant
from models.settings import Setting
from routes.restaurant_cart import get_restaurant_cart
from routes.restaurant_common import restaurant_is_open

restaurant_checkout_bp = Blueprint("restaurant_checkout", __name__)


def _whatsapp_number(restaurant):
    return "".join(ch for ch in (restaurant.whatsapp or "") if ch.isdigit())


def _render(restaurant, method, error=None):
    items, total = get_restaurant_cart(restaurant.id, method)
    if error:
        flash(error, "error")
    return render_template("restaurant/checkout.html", restaurant=restaurant, items=items, total=total, method=method, is_open=restaurant_is_open(restaurant))


@restaurant_checkout_bp.route("/comida/<slug>/checkout", methods=["GET", "POST"])
def checkout(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    method = session.get("restaurant_fulfillment_method", "delivery")
    if request.method == "GET":
        session["restaurant_checkout_form_token"] = secrets.token_urlsafe(24)
        items, _ = get_restaurant_cart(restaurant.id, method)
        if not items:
            flash("Tu carrito está vacío.", "error")
            return redirect(url_for("restaurant_cart.view", slug=slug))
        return _render(restaurant, method)

    token = request.form.get("checkout_token", "")
    if not token or token != session.get("restaurant_checkout_form_token") or token == session.get("restaurant_last_checkout_token"):
        return _render(restaurant, method, "Este formulario ya fue utilizado o venció. Actualizá la página e intentá nuevamente.")
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
            restaurant_id=restaurant.id,
            customer_name=name,
            customer_phone=phone,
            fulfillment_method=method,
            address=address if method == "delivery" else "",
            notes=notes,
            total=total,
            status="Nuevo",
        )
        db.session.add(order)
        db.session.flush()
        for item in items:
            product = item["product"]
            db.session.add(OrderItem(order_id=order.id, restaurant_product_id=product.id,
                                     product_name_snapshot=product.name, quantity=item["quantity"],
                                     unit_price=item["unit_price"], subtotal=item["subtotal"]))
        db.session.commit()
        session["restaurant_last_checkout_token"] = token
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Restaurant checkout database error")
        return _render(restaurant, method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unexpected restaurant checkout error")
        return _render(restaurant, method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")

    lines = [f"Hola {restaurant.name} 👋", "", "Quiero realizar el siguiente pedido:", "", f"Pedido #{order.id:04d}", "",
             f"Cliente: {name}", f"Teléfono: {phone}", f"Modalidad: {'Delivery' if method == 'delivery' else 'Retiro'}"]
    if method == "delivery":
        lines.append(f"Dirección: {address}")
    lines += ["", "Pedido:"]
    for item in items:
        lines.append(f"{item['quantity']}x {item['product'].name} — ${item['subtotal']:,.0f}")
    lines += ["", f"TOTAL: ${total:,.0f}", "", f"Notas: {notes or 'Sin notas'}"]
    number = _whatsapp_number(restaurant)
    whatsapp_url = f"https://wa.me/{number}?text={quote(chr(10).join(lines))}"
    session.setdefault("restaurant_cart", {}).pop(str(restaurant.id), None)
    session.modified = True
    return redirect(whatsapp_url)
