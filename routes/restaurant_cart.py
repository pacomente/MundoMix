from decimal import Decimal
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from models.restaurant import Restaurant, RestaurantProduct

restaurant_cart_bp = Blueprint("restaurant_cart", __name__)


def _cart():
    return session.setdefault("restaurant_cart", {})


def get_restaurant_cart(restaurant_id, method=None):
    method = method if method in ("delivery", "pickup") else session.get("restaurant_fulfillment_method", "delivery")
    cart = _cart()
    raw = cart.get(str(restaurant_id), {})
    items, total = [], Decimal("0.00")
    clean = {}
    for sid, raw_qty in raw.items():
        try:
            product_id, qty = int(sid), int(raw_qty)
        except (TypeError, ValueError):
            continue
        product = RestaurantProduct.query.filter_by(id=product_id, restaurant_id=restaurant_id).first()
        if not product or not product.active or product.stock <= 0:
            continue
        qty = max(1, min(qty, product.stock))
        price = Decimal(str(product.price_delivery if method == "delivery" else product.price_pickup))
        subtotal = price * qty
        clean[str(product_id)] = qty
        items.append({"product": product, "quantity": qty, "unit_price": price, "subtotal": subtotal})
        total += subtotal
    if clean:
        cart[str(restaurant_id)] = clean
    else:
        cart.pop(str(restaurant_id), None)
    session.modified = True
    return items, total


def clear_other_restaurant_carts(restaurant_id):
    cart = _cart()
    for key in list(cart):
        if key != str(restaurant_id):
            cart.pop(key, None)


@restaurant_cart_bp.post("/<slug>/carrito/agregar/<int:product_id>")
def add(slug, product_id):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    product = RestaurantProduct.query.filter_by(id=product_id, restaurant_id=restaurant.id).first_or_404()
    if not product.available:
        flash("Este producto no está disponible.", "error")
        return redirect(request.form.get("next") or url_for("restaurants.detail", slug=slug))

    existing_restaurant_ids = [key for key in _cart().keys() if key != str(restaurant.id)]
    if existing_restaurant_ids:
        return redirect(url_for("restaurants.detail", slug=slug, cart_conflict=1, conflict_product=product.id))

    qty = max(1, request.form.get("quantity", 1, type=int))
    cart = _cart()
    local_cart = cart.setdefault(str(restaurant.id), {})
    current = int(local_cart.get(str(product.id), 0))
    if current + qty > product.stock:
        flash(f"Stock insuficiente. Quedan {product.stock} unidades.", "error")
    else:
        local_cart[str(product.id)] = current + qty
        session.modified = True
        flash("Producto agregado al carrito.", "success")
    return redirect(request.form.get("next") or url_for("restaurants.detail", slug=slug))


@restaurant_cart_bp.post("/<slug>/carrito/cambiar/<int:product_id>")
def replace_cart(slug, product_id):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    product = RestaurantProduct.query.filter_by(id=product_id, restaurant_id=restaurant.id).first_or_404()
    if not product.available:
        flash("Este producto no está disponible.", "error")
        return redirect(url_for("restaurants.detail", slug=slug))
    clear_other_restaurant_carts(restaurant.id)
    _cart().setdefault(str(restaurant.id), {})[str(product.id)] = 1
    session.modified = True
    flash("Carrito cambiado al nuevo local.", "success")
    return redirect(request.form.get("next") or url_for("restaurants.detail", slug=slug))


@restaurant_cart_bp.get("/<slug>/carrito")
def view(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    method = session.get("restaurant_fulfillment_method", "delivery")
    items, total = get_restaurant_cart(restaurant.id, method)
    return render_template("restaurant/cart.html", restaurant=restaurant, items=items, total=total, method=method)


@restaurant_cart_bp.post("/<slug>/carrito/metodo")
def method(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    selected = request.form.get("fulfillment_method")
    if selected in ("delivery", "pickup"):
        session["restaurant_fulfillment_method"] = selected
        get_restaurant_cart(restaurant.id, selected)
    return redirect(request.form.get("next") or url_for("restaurant_cart.view", slug=slug))


@restaurant_cart_bp.post("/<slug>/carrito/actualizar")
def update(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    cart = _cart().setdefault(str(restaurant.id), {})
    for sid in list(cart):
        qty = request.form.get(f"qty_{sid}", type=int)
        product = RestaurantProduct.query.filter_by(id=int(sid), restaurant_id=restaurant.id).first()
        if qty is None or qty <= 0 or not product or not product.available:
            cart.pop(sid, None)
        elif qty > product.stock:
            cart[sid] = product.stock
            flash(f"{product.name}: ajustamos la cantidad al stock disponible.", "error")
        else:
            cart[sid] = qty
    session.modified = True
    return redirect(url_for("restaurant_cart.view", slug=slug))


@restaurant_cart_bp.post("/<slug>/carrito/eliminar/<int:product_id>")
def remove(slug, product_id):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    _cart().setdefault(str(restaurant.id), {}).pop(str(product_id), None)
    session.modified = True
    flash("Producto eliminado del carrito.", "success")
    return redirect(request.form.get("next") or url_for("restaurant_cart.view", slug=slug))


@restaurant_cart_bp.post("/<slug>/carrito/vaciar")
def clear(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    _cart().pop(str(restaurant.id), None)
    session.modified = True
    return redirect(url_for("restaurant_cart.view", slug=slug))
