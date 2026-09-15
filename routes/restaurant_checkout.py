from decimal import Decimal
import json, secrets
from datetime import datetime, timezone
from urllib.parse import quote
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extensions import db
from models.order import Order, OrderItem
from models.restaurant import Restaurant
from routes.restaurant_cart import get_restaurant_cart
from routes.restaurant_common import restaurant_is_open, ARG_TZ

restaurant_checkout_bp = Blueprint("restaurant_checkout", __name__)

def _whatsapp_number(r):
    return "".join(ch for ch in (r.whatsapp or "") if ch.isdigit())

def _order_whatsapp_url(order):
    r = order.restaurant
    number = _whatsapp_number(r)
    if not number:
        return None
    lines = [
        f"Hola {r.name} 👋", "", f"Pedido #{order.id:04d}",
        f"Cliente: {order.customer_name}", f"Teléfono: {order.customer_phone}",
        f"Método: {'Delivery' if order.fulfillment_method == 'delivery' else 'Retiro'}",
    ]
    if order.fulfillment_method == "delivery":
        lines += [f"Dirección: {order.address}", f"Zona: {order.delivery_zone or 'Sin especificar'}", f"Costo de envío: ${Decimal(str(order.delivery_fee or 0)):,.0f}"]
    if order.scheduled_for:
        lines.append(f"Programado para: {order.scheduled_for.replace(tzinfo=timezone.utc).astimezone(ARG_TZ).strftime('%d/%m/%Y %H:%M')}")
    lines += ["", "Productos:"]
    for i in order.items:
        lines.append(f"- {i.quantity}x {i.product_name_snapshot} — ${Decimal(str(i.subtotal)):,.0f}")
        try:
            mods = json.loads(i.modifiers_json or "[]")
        except (TypeError, ValueError):
            mods = []
        for m in mods:
            lines.append(f"  + {m.get('option')} (+${Decimal(str(m.get('price', 0))):,.0f})")
        if i.item_note:
            lines.append(f"  Nota: {i.item_note}")
    lines += ["", f"Subtotal: ${Decimal(str(order.subtotal)):,.0f}", f"Descuento: -${Decimal(str(order.discount)):,.0f}", f"Total: ${Decimal(str(order.total)):,.0f}", "", f"Notas del pedido: {order.notes or 'Sin notas'}"]
    return f"https://wa.me/{number}?text={quote(chr(10).join(lines))}"

def _delivery_fee(r, zone):
    if zone:
        for z in (r.delivery_zones or []):
            if str(z.get("name", "")).strip() == zone:
                try:
                    return Decimal(str(z.get("fee", 0)))
                except (TypeError, ValueError):
                    return Decimal("0")
    return Decimal(str(r.delivery_fee or 0))

def _render(r, method, error=None, zone=""):
    items, subtotal, discount = get_restaurant_cart(r.id, method)
    delivery = _delivery_fee(r, zone) if method == "delivery" else Decimal("0")
    total = max(Decimal("0"), subtotal - discount) + delivery
    if error:
        flash(error, "error")
    return render_template("restaurant/checkout.html", restaurant=r, items=items, subtotal=subtotal, discount=discount, delivery_fee=delivery, total=total, method=method, zone=zone, is_open=restaurant_is_open(r))

@restaurant_checkout_bp.route("/comida/<slug>/checkout", methods=["GET", "POST"])
def checkout(slug):
    r = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    method = session.get("restaurant_fulfillment_method", "delivery")
    if method == "delivery" and not r.delivery_enabled:
        method = "pickup" if r.pickup_enabled else method
    if method == "pickup" and not r.pickup_enabled:
        method = "delivery" if r.delivery_enabled else method

    if request.method == "GET":
        session["restaurant_checkout_form_token"] = secrets.token_urlsafe(24)
        items, _, _ = get_restaurant_cart(r.id, method)
        zone = request.args.get("zone", "").strip()[:160] if method == "delivery" else ""
        if not items:
            flash("Tu carrito está vacío.", "error")
            return redirect(url_for("restaurant_cart.view", slug=slug))
        return _render(r, method, zone=zone)

    token = request.form.get("checkout_token", "").strip()
    zone = request.form.get("delivery_zone", "").strip()[:160]
    if not token or token != session.get("restaurant_checkout_form_token"):
        return _render(r, method, "Este formulario venció. Actualizá la página e intentá nuevamente.", zone=zone)

    method = request.form.get("fulfillment_method", method)
    name = request.form.get("customer_name", "").strip()
    phone = request.form.get("customer_phone", "").strip()
    address = request.form.get("address", "").strip()
    notes = request.form.get("notes", "").strip()[:1000]

    if method not in ("delivery", "pickup") or (method == "delivery" and not r.delivery_enabled) or (method == "pickup" and not r.pickup_enabled):
        return _render(r, method, "El método de entrega seleccionado no está disponible.", zone=zone)
    if not name or not phone:
        return _render(r, method, "Completá nombre y teléfono/WhatsApp.", zone=zone)
    if method == "delivery" and not address:
        return _render(r, method, "La dirección es obligatoria para delivery.", zone=zone)
    if method == "delivery" and zone and not any(str(z.get("name", "")).strip() == zone for z in (r.delivery_zones or [])):
        return _render(r, method, "La zona de delivery seleccionada no es válida.", zone="")
    if not _whatsapp_number(r):
        return _render(r, method, "Este local todavía no configuró su WhatsApp.", zone=zone)
    if (not r.accept_orders) or (not restaurant_is_open(r) and not r.accept_orders_closed):
        return _render(r, method, r.pause_message or "El local no está aceptando pedidos en este momento.", zone=zone)

    scheduled = None
    if request.form.get("schedule_type") == "scheduled":
        raw = request.form.get("scheduled_for", "").strip()
        try:
            scheduled = datetime.strptime(raw, "%Y-%m-%dT%H:%M").replace(tzinfo=ARG_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return _render(r, method, "La fecha y hora programadas no son válidas.", zone=zone)
        if scheduled < datetime.utcnow():
            return _render(r, method, "El horario programado debe ser futuro.", zone=zone)

    try:
        items, subtotal, discount = get_restaurant_cart(r.id, method)
        if not items:
            return _render(r, method, "No hay productos disponibles en tu carrito.", zone=zone)
        if subtotal - discount < Decimal(str(r.minimum_order or 0)):
            return _render(r, method, f"El pedido mínimo es ${Decimal(str(r.minimum_order)):,.0f}.", zone=zone)
        delivery = _delivery_fee(r, zone) if method == "delivery" else Decimal("0")
        total = max(Decimal("0"), subtotal - discount) + delivery
        order = Order(restaurant_id=r.id, customer_name=name, customer_phone=phone, fulfillment_method=method, address=address if method == "delivery" else "", delivery_zone=zone, notes=notes, subtotal=subtotal, discount=discount, delivery_fee=delivery, total=total, scheduled_for=scheduled, status="Nuevo", checkout_token=token)
        db.session.add(order)
        db.session.flush()
        for item in items:
            db.session.add(OrderItem(order_id=order.id, restaurant_product_id=item["product"].id, product_name_snapshot=item["product"].name, quantity=item["quantity"], unit_price=item["unit_price"], modifiers_json=json.dumps(item["modifiers"], ensure_ascii=False), item_note=item["note"], subtotal=item["subtotal"]))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = Order.query.filter_by(checkout_token=token, restaurant_id=r.id).first()
        if existing:
            session.setdefault("restaurant_cart", {}).pop(str(r.id), None)
            session.pop("restaurant_checkout_form_token", None)
            return redirect(_order_whatsapp_url(existing) or url_for("restaurants.detail", slug=slug))
        return _render(r, method, "Este pedido ya fue enviado. Revisá WhatsApp antes de intentarlo nuevamente.", zone=zone)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Restaurant checkout database error")
        return _render(r, method, "No pudimos procesar tu pedido. Intentá nuevamente.", zone=zone)

    whatsapp = _order_whatsapp_url(order)
    if not whatsapp:
        return _render(r, method, "Este local no tiene un WhatsApp válido configurado.", zone=zone)
    session.setdefault("restaurant_cart", {}).pop(str(r.id), None)
    session.pop("restaurant_checkout_form_token", None)
    session["restaurant_last_checkout_token"] = token
    session.modified = True
    return redirect(whatsapp)
