from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from urllib.parse import quote
from decimal import Decimal
from extensions import db
from models.product import Product
from models.order import Order, OrderItem
from models.settings import Setting

checkout_bp = Blueprint("checkout", __name__)

def build_items(method):
    cart = session.get("cart", {})
    items, total = [], Decimal("0")
    for sid, qty in cart.items():
        product = Product.query.get(int(sid))
        if not product or not product.active or product.stock <= 0:
            continue
        qty = int(qty)
        if qty > product.stock:
            raise ValueError(f"No hay stock suficiente de {product.name}.")
        price = Decimal(str(product.price_delivery if method == "delivery" else product.price_pickup))
        subtotal = price * qty
        items.append((product, qty, price, subtotal))
        total += subtotal
    return items, total

def whatsapp_number():
    setting = Setting.query.filter_by(key="whatsapp_number").first()
    return (setting.value if setting else "") or current_app.config.get("WHATSAPP_NUMBER", "")

@checkout_bp.route("/", methods=["GET", "POST"])
def checkout():
    method = session.get("fulfillment_method", "delivery")
    if not session.get("cart"):
        flash("Tu carrito está vacío.", "error")
        return redirect(url_for("cart.view"))
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("customer_phone", "").strip()
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()
        method = request.form.get("fulfillment_method", method)
        if not name or not phone or method not in ("delivery", "pickup"):
            flash("Completá los datos obligatorios.", "error")
            try:
                items, total = build_items(method if method in ("delivery", "pickup") else "delivery")
            except ValueError as exc:
                flash(str(exc), "error")
                items, total = [], Decimal("0")
            return render_template("store/checkout.html", items=items, total=total, method=method if method in ("delivery", "pickup") else "delivery")
        if method == "delivery" and not address:
            flash("La dirección es obligatoria para envíos.", "error")
            try:
                items, total = build_items(method)
            except ValueError as exc:
                flash(str(exc), "error")
                items, total = [], Decimal("0")
            return render_template("store/checkout.html", items=items, total=total, method=method)
        try:
            items, total = build_items(method)
            if not items:
                raise ValueError("No hay productos disponibles.")
            order = Order(customer_name=name, customer_phone=phone, fulfillment_method=method,
                          address=address if method == "delivery" else "", notes=notes, total=total, status="Nuevo")
            db.session.add(order)
            db.session.flush()
            for product, qty, price, subtotal in items:
                db.session.add(OrderItem(order_id=order.id, product_id=product.id,
                                         product_name_snapshot=product.name, quantity=qty,
                                         unit_price=price, subtotal=subtotal))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "error")
            items, total = build_items(method)
            return render_template("store/checkout.html", items=items, total=total, method=method)

        number = whatsapp_number().replace("+", "").replace(" ", "").replace("-", "")
        lines = ["MundoMix — Nuevo pedido", f"Pedido #{order.id:04d}", "", f"Cliente: {name}", f"Teléfono: {phone}",
                 f"Método: {'Envío' if method == 'delivery' else 'Retiro en local'}"]
        if method == "delivery":
            lines.append(f"Dirección: {address}")
        lines += ["", "Productos:"]
        for product, qty, price, subtotal in items:
            lines.append(f"{product.name} x{qty} — ${subtotal:,.0f}")
        lines += ["", f"Total: ${total:,.0f}", f"Notas: {notes or 'Sin notas'}"]
        whatsapp_url = f"https://wa.me/{number}?text={quote(chr(10).join(lines))}" if number else ""
        session["cart"] = {}
        session["fulfillment_method"] = method
        session.modified = True
        return render_template("store/order_success.html", order=order, whatsapp_url=whatsapp_url)

    items, total = build_items(method)
    return render_template("store/checkout.html", items=items, total=total, method=method)
