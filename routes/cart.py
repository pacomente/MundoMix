from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models.product import Product

cart_bp = Blueprint("cart", __name__)


def get_cart():
    cart = session.get("cart")
    if not isinstance(cart, dict):
        cart = {}
        session["cart"] = cart
    return cart


def _product_from_session_id(sid):
    try:
        return Product.query.get(int(sid))
    except (TypeError, ValueError):
        return None


def cart_items(method=None):
    method = method if method in ("delivery", "pickup") else session.get("fulfillment_method", "delivery")
    if method not in ("delivery", "pickup"):
        method = "delivery"
    items, total = [], Decimal("0")
    cart = get_cart()
    for sid, raw_qty in list(cart.items()):
        product = _product_from_session_id(sid)
        try:
            qty = int(raw_qty)
        except (TypeError, ValueError):
            cart.pop(sid, None)
            continue
        if not product or not product.active or product.stock <= 0 or qty <= 0:
            cart.pop(sid, None)
            continue
        qty = min(qty, product.stock)
        cart[str(product.id)] = qty
        if str(product.id) != str(sid):
            cart.pop(sid, None)
        price = Decimal(str(product.price_delivery if method == "delivery" else product.price_pickup))
        subtotal = price * qty
        items.append({"product": product, "quantity": qty, "unit_price": price, "subtotal": subtotal})
        total += subtotal
    session.modified = True
    return items, total


@cart_bp.get("/")
def view():
    method = session.get("fulfillment_method", "delivery")
    items, total = cart_items(method)
    return render_template("store/cart.html", items=items, total=total, method=method)


@cart_bp.post("/agregar/<int:product_id>")
def add(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.available:
        flash("Este producto no está disponible.", "error")
        return redirect(request.referrer or url_for("store.catalog"))
    qty = max(1, request.form.get("quantity", 1, type=int))
    cart = get_cart()
    try:
        current = max(0, int(cart.get(str(product_id), 0)))
    except (TypeError, ValueError):
        current = 0
    if current + qty > product.stock:
        flash(f"Stock insuficiente. Quedan {product.stock} unidades.", "error")
    else:
        cart[str(product_id)] = current + qty
        session.modified = True
        flash("Producto agregado al carrito.", "success")
    next_url = request.form.get("next")
    return redirect(next_url if next_url and next_url.startswith("/") and not next_url.startswith("//") else request.referrer or url_for("store.catalog"))


@cart_bp.post("/actualizar")
def update():
    cart = get_cart()
    for sid in list(cart):
        product = _product_from_session_id(sid)
        qty = request.form.get(f"qty_{sid}", type=int)
        if qty is None or qty <= 0 or not product or not product.active or product.stock <= 0:
            cart.pop(sid, None)
        elif qty > product.stock:
            cart[sid] = product.stock
            flash(f"{product.name}: ajustamos la cantidad al stock disponible.", "error")
        else:
            cart[sid] = qty
    session.modified = True
    return redirect(url_for("cart.view"))


@cart_bp.post("/metodo")
def method():
    selected = request.form.get("fulfillment_method")
    if selected in ("delivery", "pickup"):
        session["fulfillment_method"] = selected
    next_url = request.form.get("next")
    return redirect(next_url if next_url and next_url.startswith("/") and not next_url.startswith("//") else url_for("cart.view"))


@cart_bp.post("/eliminar/<int:product_id>")
def remove(product_id):
    get_cart().pop(str(product_id), None)
    session.modified = True
    flash("Producto eliminado del carrito.", "success")
    next_url = request.form.get("next")
    return redirect(next_url if next_url and next_url.startswith("/") and not next_url.startswith("//") else url_for("cart.view"))


@cart_bp.post("/vaciar")
def clear():
    session["cart"] = {}
    session.modified = True
    return redirect(url_for("cart.view"))
