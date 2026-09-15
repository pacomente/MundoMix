import hashlib, json
from decimal import Decimal
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from models.restaurant import Restaurant, RestaurantProduct, ModifierOption, ModifierGroup, RestaurantPromotion
from routes.restaurant_common import restaurant_is_open

restaurant_cart_bp = Blueprint("restaurant_cart", __name__)

def _cart(): return session.setdefault("restaurant_cart", {})

def _line_key(product_id, modifiers, note):
    raw = json.dumps([product_id, sorted(modifiers), note], ensure_ascii=False)
    return f"{product_id}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

def _parse_modifiers(product):
    try: selected = json.loads(request.form.get("modifiers_json", "[]"))
    except (TypeError, ValueError): raise ValueError("Las opciones seleccionadas no son válidas.")
    if not isinstance(selected, list): raise ValueError("Las opciones seleccionadas no son válidas.")
    selected = [int(x) for x in selected if str(x).isdigit()]
    groups = [link.group for link in product.modifier_links if link.group.active]
    valid = {o.id: o for g in groups for o in g.options if o.active}
    selected = list(dict.fromkeys(selected))
    if any(x not in valid for x in selected): raise ValueError("Una de las opciones ya no está disponible.")
    by_group = {}
    for oid in selected: by_group.setdefault(valid[oid].group_id, []).append(valid[oid])
    result=[]; extra=Decimal("0")
    for group in groups:
        choices=by_group.get(group.id, [])
        if len(choices) < group.min_choices: raise ValueError(f"Elegí al menos {group.min_choices} opción(es) en {group.name}.")
        if group.max_choices and len(choices) > group.max_choices: raise ValueError(f"Elegí como máximo {group.max_choices} opción(es) en {group.name}.")
        for option in choices:
            delta=Decimal(str(option.price_delta)); extra += delta
            result.append({"group": group.name, "option": option.name, "price": str(delta), "option_id": option.id})
    return result, extra

def _active_promotion(product, now=None):
    from datetime import datetime
    now = now or datetime.utcnow()
    promos = RestaurantPromotion.query.filter_by(restaurant_id=product.restaurant_id, active=True).filter((RestaurantPromotion.product_id == product.id) | (RestaurantPromotion.product_id.is_(None))).all()
    valid=[]
    for p in promos:
        if p.starts_at and now < p.starts_at: continue
        if p.ends_at and now > p.ends_at: continue
        valid.append(p)
    return sorted(valid, key=lambda p: p.product_id is None)[0] if valid else None

def _line_discount(product, qty, base):
    promo=_active_promotion(product)
    if not promo or qty < max(1, promo.min_quantity): return Decimal("0"), None
    if promo.promotion_type == "2x1":
        return base * (qty // 2), promo
    if promo.promotion_type == "percentage":
        return (base * Decimal(str(promo.value)) / Decimal("100")), promo
    if promo.promotion_type == "fixed":
        return min(base, Decimal(str(promo.value))), promo
    return Decimal("0"), None

def get_restaurant_cart(restaurant_id, method=None):
    method = method if method in ("delivery", "pickup") else session.get("restaurant_fulfillment_method", "delivery")
    cart = _cart(); raw=cart.get(str(restaurant_id), {})
    items=[]; subtotal=Decimal("0"); discount=Decimal("0"); clean={}
    for line_id, raw_line in raw.items():
        # Backwards-compatible legacy session format: {product_id: quantity}
        if isinstance(raw_line, dict):
            product_id=int(raw_line.get("product_id", 0)); qty=int(raw_line.get("quantity", 0)); modifiers=raw_line.get("modifiers", []); note=str(raw_line.get("note", ""))[:500]
        else:
            try: product_id=int(line_id); qty=int(raw_line); modifiers=[]; note=""
            except (TypeError, ValueError): continue
        product=RestaurantProduct.query.filter_by(id=product_id, restaurant_id=restaurant_id).first()
        if not product or not product.available: continue
        if product.stock_control: qty=min(qty, product.stock)
        qty=max(1, qty)
        unit=Decimal(str(product.price_delivery if method=="delivery" else product.price_pickup))
        extra=Decimal("0")
        mod_snapshot=[]
        if modifiers:
            valid={o.id:o for l in product.modifier_links for o in l.group.options if l.group.active and o.active}
            for oid in modifiers:
                if int(oid) in valid:
                    o=valid[int(oid)]; d=Decimal(str(o.price_delta)); extra+=d; mod_snapshot.append({"group":o.group.name,"option":o.name,"price":str(d),"option_id":o.id})
        line_base=(unit+extra)*qty
        line_discount,promo=_line_discount(product, qty, line_base)
        line_total=max(Decimal("0"), line_base-line_discount)
        clean[line_id]={"product_id":product.id,"quantity":qty,"modifiers":[x.get("option_id") for x in mod_snapshot],"note":note}
        items.append({"product":product,"quantity":qty,"unit_price":unit+extra,"base_unit_price":unit,"modifiers":mod_snapshot,"note":note,"subtotal":line_total,"line_base":line_base,"discount":line_discount,"promotion":promo,"line_id":line_id})
        subtotal += line_base; discount += line_discount
    if clean: cart[str(restaurant_id)]=clean
    else: cart.pop(str(restaurant_id),None)
    session.modified=True
    return items, subtotal, discount

def clear_other_restaurant_carts(restaurant_id):
    cart=_cart()
    for key in list(cart):
        if key != str(restaurant_id): cart.pop(key,None)

def _save_line(restaurant, product, qty, modifiers, note):
    line_id=_line_key(product.id, modifiers, note)
    local=_cart().setdefault(str(restaurant.id), {})
    existing=local.get(line_id, {})
    current=int(existing.get("quantity",0)) if isinstance(existing,dict) else int(existing or 0)
    if product.stock_control and current+qty>product.stock: raise ValueError(f"Stock insuficiente. Quedan {product.stock} unidades.")
    local[line_id]={"product_id":product.id,"quantity":current+qty,"modifiers":modifiers,"note":note}
    session.modified=True

@restaurant_cart_bp.post("/<slug>/carrito/agregar/<int:product_id>")
def add(slug, product_id):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); product=RestaurantProduct.query.filter_by(id=product_id,restaurant_id=restaurant.id).first_or_404()
    if not product.available: flash("Este producto está agotado o no disponible.","error"); return redirect(request.form.get("next") or url_for("restaurants.detail",slug=slug))
    if any(k!=str(restaurant.id) for k in _cart()): return redirect(url_for("restaurants.detail",slug=slug,cart_conflict=1,conflict_product=product.id))
    try:
        modifiers,_extra=_parse_modifiers(product); note=request.form.get("item_note","").strip()[:500]; qty=max(1,request.form.get("quantity",1,type=int)); _save_line(restaurant,product,qty,[x["option_id"] for x in modifiers],note); flash("Producto agregado al carrito.","success")
    except ValueError as exc: flash(str(exc),"error")
    return redirect(request.form.get("next") or url_for("restaurants.detail",slug=slug))

@restaurant_cart_bp.post("/<slug>/carrito/cambiar/<int:product_id>")
def replace_cart(slug,product_id):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); product=RestaurantProduct.query.filter_by(id=product_id,restaurant_id=restaurant.id).first_or_404()
    if not product.available: flash("Este producto no está disponible.","error"); return redirect(url_for("restaurants.detail",slug=slug))
    clear_other_restaurant_carts(restaurant.id)
    try:
        modifiers,_=_parse_modifiers(product); _save_line(restaurant,product,1,[x["option_id"] for x in modifiers],request.form.get("item_note","").strip()[:500]); flash("Carrito cambiado al nuevo local.","success")
    except ValueError as exc: flash(str(exc),"error")
    return redirect(request.form.get("next") or url_for("restaurants.detail",slug=slug))

@restaurant_cart_bp.get("/<slug>/carrito")
def view(slug):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); method=session.get("restaurant_fulfillment_method","delivery")
    items,subtotal,discount=get_restaurant_cart(restaurant.id,method); delivery_fee=Decimal(str(restaurant.delivery_fee or 0)) if method=="delivery" else Decimal("0")
    total=max(Decimal("0"),subtotal-discount)+delivery_fee
    return render_template("restaurant/cart.html",restaurant=restaurant,items=items,subtotal=subtotal,discount=discount,delivery_fee=delivery_fee,total=total,method=method)

@restaurant_cart_bp.post("/<slug>/carrito/metodo")
def method(slug):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); selected=request.form.get("fulfillment_method")
    if selected=="delivery" and not restaurant.delivery_enabled: flash("Este local no ofrece delivery.","error")
    elif selected=="pickup" and not restaurant.pickup_enabled: flash("Este local no ofrece retiro.","error")
    elif selected in ("delivery","pickup"): session["restaurant_fulfillment_method"]=selected; get_restaurant_cart(restaurant.id,selected)
    return redirect(request.form.get("next") or url_for("restaurant_cart.view",slug=slug))

@restaurant_cart_bp.post("/<slug>/carrito/actualizar")
def update(slug):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); cart=_cart().setdefault(str(restaurant.id),{})
    for line_id,line in list(cart.items()):
        qty=request.form.get(f"qty_{line_id}",type=int)
        if qty is None or qty<=0: cart.pop(line_id,None); continue
        product_id=line.get("product_id") if isinstance(line,dict) else int(line_id); product=RestaurantProduct.query.filter_by(id=product_id,restaurant_id=restaurant.id).first()
        if not product or not product.available: cart.pop(line_id,None); continue
        if product.stock_control and qty>product.stock: qty=product.stock; flash(f"{product.name}: ajustamos la cantidad al stock disponible.","error")
        cart[line_id]["quantity"]=qty
    session.modified=True; return redirect(url_for("restaurant_cart.view",slug=slug))

@restaurant_cart_bp.post("/<slug>/carrito/eliminar/<path:line_id>")
def remove(slug,line_id):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); _cart().setdefault(str(restaurant.id),{}).pop(line_id,None); session.modified=True
    return redirect(request.form.get("next") or url_for("restaurant_cart.view",slug=slug))

@restaurant_cart_bp.post("/<slug>/carrito/vaciar")
def clear(slug):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); _cart().pop(str(restaurant.id),None); session.modified=True; return redirect(url_for("restaurant_cart.view",slug=slug))
