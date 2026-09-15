from flask import Blueprint, render_template, request, abort
from sqlalchemy import or_, asc
from models.restaurant import Restaurant, RestaurantCategory, RestaurantProduct
from routes.restaurant_common import restaurant_is_open

restaurants_bp = Blueprint("restaurants", __name__)


@restaurants_bp.get("/comida")
def index():
    q = request.args.get("q", "").strip()
    food_type = request.args.get("food_type", "").strip()
    query = Restaurant.query.filter_by(active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Restaurant.name.ilike(like), Restaurant.description.ilike(like), Restaurant.food_type.ilike(like), Restaurant.address.ilike(like)))
    if food_type:
        query = query.filter(Restaurant.food_type == food_type)
    restaurants = query.order_by(asc(Restaurant.name)).all()
    food_types = [x[0] for x in Restaurant.query.with_entities(Restaurant.food_type).filter(Restaurant.active.is_(True), Restaurant.food_type.isnot(None), Restaurant.food_type != "").distinct().order_by(Restaurant.food_type).all()]
    return render_template("restaurant/index.html", restaurants=restaurants, q=q, food_type=food_type, food_types=food_types, restaurant_is_open=restaurant_is_open)


@restaurants_bp.get("/comida/<slug>")
def detail(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, active=True).first_or_404()
    categories = (RestaurantCategory.query.filter_by(restaurant_id=restaurant.id, active=True)
                  .order_by(RestaurantCategory.display_order, RestaurantCategory.name).all())
    uncategorized = RestaurantProduct.query.filter_by(restaurant_id=restaurant.id, category_id=None, active=True).order_by(RestaurantProduct.name).all()
    grouped = [(category, RestaurantProduct.query.filter_by(restaurant_id=restaurant.id, category_id=category.id, active=True).order_by(RestaurantProduct.name).all()) for category in categories]
    return render_template("restaurant/detail.html", restaurant=restaurant, categories=grouped, uncategorized=uncategorized, restaurant_is_open=restaurant_is_open(restaurant))
