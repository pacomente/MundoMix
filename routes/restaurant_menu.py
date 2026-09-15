from decimal import Decimal, InvalidOperation
from flask import Blueprint, flash, redirect, render_template, request, url_for, session
from sqlalchemy.exc import SQLAlchemyError
from extensions import db
from models.restaurant import Restaurant, ModifierGroup, ModifierOption, ProductModifierGroup, RestaurantPromotion, RestaurantProduct
from routes.restaurant_auth import restaurant_required
from datetime import datetime

restaurant_menu_bp=Blueprint("restaurant_menu",__name__)
def current_restaurant():
    rid=session.get("restaurant_id")
    return db.session.get(Restaurant,rid) if rid else None
def money(value):
    try: x=Decimal(str(value).replace(",","."))
    except (InvalidOperation,TypeError): raise ValueError("Ingresá un precio válido.")
    if x<0: raise ValueError("El precio no puede ser negativo.")
    return x

def _int(name,default=0):
    try:return int(request.form.get(name,default))
    except (TypeError,ValueError):return default

@restaurant_menu_bp.get("/comercio/panel/modificadores")
@restaurant_required
def modifiers():
    r=current_restaurant(); groups=ModifierGroup.query.filter_by(restaurant_id=r.id).order_by(ModifierGroup.display_order,ModifierGroup.name).all()
    return render_template("restaurant/panel/modifiers.html",restaurant=r,groups=groups)

@restaurant_menu_bp.post("/comercio/panel/modificadores/grupo")
@restaurant_required
def modifier_group_create():
    r=current_restaurant(); name=request.form.get("name","").strip()
    if not name: flash("El nombre del grupo es obligatorio.","error")
    else:
        g=ModifierGroup(restaurant_id=r.id,name=name,min_choices=max(0,_int("min_choices")),max_choices=max(0,_int("max_choices",1)),display_order=_int("display_order"),active=True); db.session.add(g); db.session.commit(); flash("Grupo de opciones creado.","success")
    return redirect(url_for("restaurant_menu.modifiers"))

@restaurant_menu_bp.post("/comercio/panel/modificadores/grupo/<int:id>/opcion")
@restaurant_required
def modifier_option_create(id):
    r=current_restaurant(); g=ModifierGroup.query.filter_by(id=id,restaurant_id=r.id).first_or_404(); name=request.form.get("name","").strip()
    if not name: flash("El nombre de la opción es obligatorio.","error")
    else:
        try: price=money(request.form.get("price_delta","0"))
        except ValueError as exc: flash(str(exc),"error"); return redirect(url_for("restaurant_menu.modifiers"))
        db.session.add(ModifierOption(group_id=g.id,name=name,price_delta=price,display_order=_int("display_order"),active=True)); db.session.commit(); flash("Opción agregada.","success")
    return redirect(url_for("restaurant_menu.modifiers"))

@restaurant_menu_bp.post("/comercio/panel/modificadores/opcion/<int:id>/toggle")
@restaurant_required
def modifier_option_toggle(id):
    r=current_restaurant(); o=ModifierOption.query.join(ModifierGroup).filter(ModifierOption.id==id,ModifierGroup.restaurant_id==r.id).first_or_404(); o.active=not o.active; db.session.commit(); return redirect(url_for("restaurant_menu.modifiers"))

@restaurant_menu_bp.post("/comercio/panel/modificadores/grupo/<int:id>/toggle")
@restaurant_required
def modifier_group_toggle(id):
    r=current_restaurant(); g=ModifierGroup.query.filter_by(id=id,restaurant_id=r.id).first_or_404(); g.active=not g.active; db.session.commit(); return redirect(url_for("restaurant_menu.modifiers"))

@restaurant_menu_bp.get("/comercio/panel/promociones")
@restaurant_required
def promotions():
    r=current_restaurant(); promos=RestaurantPromotion.query.filter_by(restaurant_id=r.id).order_by(RestaurantPromotion.active.desc(),RestaurantPromotion.name).all(); products=RestaurantProduct.query.filter_by(restaurant_id=r.id).order_by(RestaurantProduct.name).all()
    return render_template("restaurant/panel/promotions.html",restaurant=r,promotions=promos,products=products)

@restaurant_menu_bp.post("/comercio/panel/promociones")
@restaurant_required
def promotion_create():
    r=current_restaurant(); name=request.form.get("name","").strip(); ptype=request.form.get("promotion_type","percentage")
    try:value=money(request.form.get("value","0"))
    except ValueError as exc: flash(str(exc),"error"); return redirect(url_for("restaurant_menu.promotions"))
    if not name or ptype not in ("percentage","fixed","2x1"): flash("Completá la promoción correctamente.","error"); return redirect(url_for("restaurant_menu.promotions"))
    product_id=request.form.get("product_id",type=int) or None
    if product_id and not RestaurantProduct.query.filter_by(id=product_id,restaurant_id=r.id).first(): flash("Producto inválido.","error"); return redirect(url_for("restaurant_menu.promotions"))
    def dt(field):
        raw=request.form.get(field,"").strip()
        if not raw:return None
        try:return datetime.strptime(raw,"%Y-%m-%dT%H:%M")
        except ValueError:return None
    db.session.add(RestaurantPromotion(restaurant_id=r.id,name=name,promotion_type=ptype,value=value,product_id=product_id,min_quantity=max(1,_int("min_quantity",2)),starts_at=dt("starts_at"),ends_at=dt("ends_at"),active=True)); db.session.commit(); flash("Promoción creada.","success"); return redirect(url_for("restaurant_menu.promotions"))

@restaurant_menu_bp.post("/comercio/panel/promociones/<int:id>/toggle")
@restaurant_required
def promotion_toggle(id):
    r=current_restaurant(); p=RestaurantPromotion.query.filter_by(id=id,restaurant_id=r.id).first_or_404(); p.active=not p.active; db.session.commit(); return redirect(url_for("restaurant_menu.promotions"))
