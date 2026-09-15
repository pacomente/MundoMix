from decimal import Decimal
import secrets
from urllib.parse import quote

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models.order import Order, OrderItem
from models.product import Product
from models.settings import Setting

checkout_bp = Blueprint("checkout", __name__)


def _normalise_method(value):
    return value if value in ("delivery", "pickup") else "delivery"


def build_items(method):
    """Rebuild checkout totals from PostgreSQL, never trusting client prices."""
    method = _normalise_method(method)
    cart = session.get("cart") or {}
    items = []
    total = Decimal("0.00")

    for sid, raw_qty in list(cart.items()):
        try:
            product_id = int(sid)
            qty = int(raw_qty)
        except (TypeError, ValueError):
            continue

        if qty <= 0:
            continue

        product = db.session.get(Product, product_id)
        if not product or not product.active:
            continue
        if product.stock <= 0:
            continue
        if qty > product.stock:
            raise ValueError(f"No hay stock suficiente de {product.name}. Quedan {product.stock} unidades.")

        price_value = product.price_delivery if method == "delivery" else product.price_pickup
        price = Decimal(str(price_value))
        subtotal = price * qty
        items.append((product, qty, price, subtotal))
        total += subtotal

    return items, total


def whatsapp_number():
    setting = Setting.query.filter_by(key="whatsapp_number").first()
    return (setting.value if setting else "") or current_app.config.get("WHATSAPP_NUMBER", "")


def render_checkout(method, message=None):
    method = _normalise_method(method)
    try:
        items, total = build_items(method)
    except ValueError as exc:
        flash(str(exc), "error")
        items, total = [], Decimal("0.00")

    if message:
        flash(message, "error")
    return render_template(
        "store/checkout.html",
        items=items,
        total=total,
        method=method,
    )


@checkout_bp.route("/", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart") or {}
    if not cart:
        flash("Tu carrito está vacío.", "error")
        return redirect(url_for("cart.view"))

    method = _normalise_method(session.get("fulfillment_method", "delivery"))

    if request.method == "GET":
        # One token per rendered checkout protects against accidental double-submit
        # without introducing a new dependency or changing the existing session architecture.
        session["checkout_form_token"] = secrets.token_urlsafe(24)
        return render_checkout(method)

    # Basic duplicate-submit protection for the same browser session.
    checkout_token = request.form.get("checkout_token", "").strip()
    if not checkout_token:
        return render_checkout(method, "No se pudo validar el formulario. Actualizá la página e intentá nuevamente.")
    if checkout_token == session.get("last_checkout_token"):
        return render_checkout(method, "Este pedido ya fue enviado. Revisá la pantalla anterior antes de volver a intentarlo.")

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

        for product, qty, price, subtotal in items:
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name_snapshot=product.name,
                    quantity=qty,
                    unit_price=price,
                    subtotal=subtotal,
                )
            )

        # Do not reduce stock here: MundoMix currently reduces it when the
        # order is confirmed from the admin panel. Keep that business rule.
        db.session.commit()
        session["last_checkout_token"] = checkout_token

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Checkout PostgreSQL/SQLAlchemy error")
        return render_checkout(method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unexpected MundoMix checkout error")
        return render_checkout(method, "No pudimos procesar tu pedido en este momento. Intentá nuevamente.")

    number = "".join(ch for ch in whatsapp_number() if ch.isdigit())
    lines = [
        "MundoMix — Nuevo pedido",
        f"Pedido #{order.id:04d}",
        "",
        f"Cliente: {name}",
        f"Teléfono: {phone}",
        f"Método: {'Envío' if method == 'delivery' else 'Retiro en local'}",
    ]
    if method == "delivery":
        lines.append(f"Dirección: {address}")
    lines += ["", "Productos:"]
    for product, qty, price, subtotal in items:
        lines.append(f"{product.name} x{qty} — ${subtotal:,.0f}")
    lines += ["", f"Total: ${total:,.0f}", f"Notas: {notes or 'Sin notas'}"]

    whatsapp_url = f"https://wa.me/{number}?text={quote(chr(10).join(lines))}" if number else ""

    # Clear the cart only after the DB transaction has committed successfully.
    session["cart"] = {}
    session["fulfillment_method"] = method
    session.modified = True

    if whatsapp_url:
        return redirect(whatsapp_url)

    # The order is already safely stored. Show a useful fallback if WhatsApp
    # has not been configured by the administrator.
    return render_template("store/order_success.html", order=order, whatsapp_url="")
