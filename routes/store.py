from flask import Blueprint, render_template, request
from sqlalchemy import or_, asc, desc
from extensions import db
from models.product import Product
from models.category import Category
from models.banner import Banner

store_bp = Blueprint("store", __name__)

@store_bp.route("/")
def index():
    banners = Banner.query.filter_by(active=True).order_by(asc(Banner.display_order), asc(Banner.id)).all()
    featured = Product.query.filter_by(active=True, featured=True).order_by(desc(Product.created_at)).limit(8).all()
    offers = Product.query.filter_by(active=True).order_by(desc(Product.created_at)).limit(8).all()
    categories = Category.query.filter_by(active=True).order_by(Category.name).all()
    return render_template("store/index.html", banners=banners, featured=featured, offers=offers, categories=categories)

@store_bp.route("/catalogo")
def catalog():
    page = max(request.args.get("page", 1, type=int), 1)
    query = Product.query.filter_by(active=True)
    category = request.args.get("category", "").strip()
    q = request.args.get("q", "").strip()
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    availability = request.args.get("availability", "")
    featured = request.args.get("featured", "")
    sort = request.args.get("sort", "relevance")

    if q:
        like = f"%{q}%"
        query = query.outerjoin(Category).filter(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.description.ilike(like), Category.name.ilike(like)))
    if category:
        query = query.join(Category).filter(Category.slug == category)
    if min_price is not None:
        query = query.filter(Product.price_pickup >= min_price)
    if max_price is not None:
        query = query.filter(Product.price_pickup <= max_price)
    if availability == "available":
        query = query.filter(Product.stock > 0)
    if featured == "1":
        query = query.filter(Product.featured.is_(True))

    ordering = {
        "price_asc": asc(Product.price_pickup),
        "price_desc": desc(Product.price_pickup),
        "newest": desc(Product.created_at),
        "name_asc": asc(Product.name),
        "name_desc": desc(Product.name),
    }
    query = query.order_by(ordering.get(sort, desc(Product.featured)), desc(Product.created_at))
    pagination = query.paginate(page=page, per_page=12, error_out=False)
    categories = Category.query.filter_by(active=True).order_by(Category.name).all()
    return render_template("store/catalog.html", products=pagination.items, pagination=pagination, categories=categories,
                           q=q, selected_category=category, min_price=min_price, max_price=max_price,
                           availability=availability, featured=featured, sort=sort)

@store_bp.route("/producto/<slug>")
def product(slug):
    item = Product.query.filter_by(slug=slug, active=True).first_or_404()
    related = Product.query.filter(Product.active.is_(True), Product.id != item.id, Product.category_id == item.category_id).order_by(desc(Product.created_at)).limit(4).all() if item.category_id else []
    return render_template("store/product.html", product=item, related=related)

@store_bp.route("/buscar")
def search():
    return catalog()
