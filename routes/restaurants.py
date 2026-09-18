from flask import Blueprint, render_template, request, url_for
from sqlalchemy import or_, asc, desc
from sqlalchemy.orm import selectinload
from models.restaurant import Restaurant, RestaurantCategory, RestaurantProduct, ProductModifierGroup, ModifierGroup, ModifierOption
from routes.restaurant_common import restaurant_is_open
restaurants_bp=Blueprint("restaurants",__name__)

@restaurants_bp.get("/comida")
def index():
    q=request.args.get("q","").strip(); food_type=request.args.get("food_type","").strip(); sort=request.args.get("sort","name"); open_now=request.args.get("open_now")=="1"; featured=request.args.get("featured")=="1"
    query=Restaurant.query.filter_by(active=True).options(selectinload(Restaurant.products), selectinload(Restaurant.categories))
    if q:
        like=f"%{q}%"
        category_ids=[x[0] for x in RestaurantCategory.query.with_entities(RestaurantCategory.restaurant_id).filter(RestaurantCategory.active.is_(True),RestaurantCategory.name.ilike(like)).distinct().all()]
        product_ids=[x[0] for x in RestaurantProduct.query.with_entities(RestaurantProduct.restaurant_id).filter(RestaurantProduct.active.is_(True),or_(RestaurantProduct.name.ilike(like),RestaurantProduct.description.ilike(like))).distinct().all()]
        product_ids=list(set(product_ids+category_ids))
        query=query.filter(or_(Restaurant.name.ilike(like),Restaurant.description.ilike(like),Restaurant.food_type.ilike(like),Restaurant.address.ilike(like),Restaurant.id.in_(product_ids)))
    if food_type: query=query.filter(Restaurant.food_type==food_type)
    if featured: query=query.filter(Restaurant.products.any(RestaurantProduct.featured.is_(True),RestaurantProduct.active.is_(True)))
    restaurants=query.all()
    if open_now: restaurants=[r for r in restaurants if restaurant_is_open(r)]
    if sort=="new": restaurants.sort(key=lambda r:r.created_at,reverse=True)
    elif sort=="name": restaurants.sort(key=lambda r:r.name.lower())
    food_types=[x[0] for x in Restaurant.query.with_entities(Restaurant.food_type).filter(Restaurant.active.is_(True),Restaurant.food_type.isnot(None),Restaurant.food_type!="").distinct().order_by(Restaurant.food_type).all()]
    return render_template("restaurant/index.html",restaurants=restaurants,q=q,food_type=food_type,food_types=food_types,sort=sort,open_now=open_now,featured=featured,restaurant_is_open=restaurant_is_open)

@restaurants_bp.get("/comida/<slug>")
def detail(slug):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).options(selectinload(Restaurant.categories),selectinload(Restaurant.products).selectinload(RestaurantProduct.modifier_links).selectinload(ProductModifierGroup.group).selectinload(ModifierGroup.options)).first_or_404()
    categories=[c for c in restaurant.categories if c.active]
    bycat={c.id:[] for c in categories}; uncategorized=[]
    for p in sorted([p for p in restaurant.products if p.active],key=lambda p:(p.display_order,p.name.lower())):
        if p.category_id in bycat: bycat[p.category_id].append(p)
        else: uncategorized.append(p)
    grouped=[(c,bycat[c.id]) for c in sorted(categories,key=lambda c:(c.display_order,c.name.lower())) if bycat[c.id]]
    return render_template("restaurant/detail.html",restaurant=restaurant,categories=grouped,uncategorized=uncategorized,restaurant_is_open=restaurant_is_open(restaurant),canonical=url_for("restaurants.detail",slug=restaurant.slug,_external=True))

@restaurants_bp.get("/comida/<slug>/producto/<product_slug>")
def product_detail(slug,product_slug):
    restaurant=Restaurant.query.filter_by(slug=slug,active=True).first_or_404(); product=RestaurantProduct.query.filter_by(restaurant_id=restaurant.id,slug=product_slug,active=True).options(selectinload(RestaurantProduct.modifier_links).selectinload(ProductModifierGroup.group).selectinload(ModifierGroup.options)).first_or_404()
    return render_template("restaurant/product.html",restaurant=restaurant,product=product,restaurant_is_open=restaurant_is_open(restaurant))
