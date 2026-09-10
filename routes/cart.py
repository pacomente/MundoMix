from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.product import Product

cart_bp = Blueprint("cart", __name__)

def get_cart():
    return session.setdefault("cart", {})

def cart_items(method=None):
    method = method or session.get("fulfillment_method", "delivery")
    items, total = [], Decimal("0")
    cart = get_cart()
    for sid, qty in list(cart.items()):
        product = Product.query.get(int(sid))
        if not product or not product.active or product.stock <= 0:
            cart.pop(sid, None)
            continue
        qty = min(max(int(qty), 1), product.stock)
        cart[sid] = qty
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
    current = int(cart.get(str(product_id), 0))
    if current + qty > product.stock:
        flash(f"Stock insuficiente. Quedan {product.stock} unidades.", "error")
    else:
        cart[str(product_id)] = current + qty
        session.modified = True
        flash("Producto agregado al carrito.", "success")
    return redirect(request.form.get("next") or request.referrer or url_for("store.catalog"))

@cart_bp.post("/actualizar")
def update():
    cart = get_cart()
    for sid in list(cart):
        qty = request.form.get(f"qty_{sid}", type=int)
        product = Product.query.get(int(sid))
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
    return redirect(request.form.get("next") or url_for("cart.view"))

@cart_bp.post("/eliminar/<int:product_id>")
def remove(product_id):
    get_cart().pop(str(product_id), None)
    session.modified = True
    flash("Producto eliminado del carrito.", "success")
    return redirect(request.form.get("next") or url_for("cart.view"))

@cart_bp.post("/vaciar")
def clear():
    session["cart"] = {}
    return redirect(url_for("cart.view"))
