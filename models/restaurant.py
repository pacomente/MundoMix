from datetime import datetime
from extensions import db


class Restaurant(db.Model):
    __tablename__ = "restaurant"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    food_type = db.Column(db.String(120), default="Comida rápida")
    logo = db.Column(db.String(255))
    banner = db.Column(db.String(255))
    address = db.Column(db.String(300), default="")
    phone = db.Column(db.String(40), default="")
    whatsapp = db.Column(db.String(40), default="")
    instagram = db.Column(db.String(300), default="")
    facebook = db.Column(db.String(300), default="")
    meta_title = db.Column(db.String(180), default="")
    meta_description = db.Column(db.String(300), default="")
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    accept_orders_closed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    users = db.relationship("RestaurantUser", back_populates="restaurant", cascade="all, delete-orphan")
    categories = db.relationship("RestaurantCategory", back_populates="restaurant", cascade="all, delete-orphan", passive_deletes=True)
    products = db.relationship("RestaurantProduct", back_populates="restaurant", cascade="all, delete-orphan", passive_deletes=True)
    orders = db.relationship("Order", back_populates="restaurant")
    hours = db.relationship("RestaurantHour", back_populates="restaurant", cascade="all, delete-orphan", order_by="RestaurantHour.weekday")


class RestaurantUser(db.Model):
    __tablename__ = "restaurant_user"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False, index=True)
    username = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="users")


class RestaurantCategory(db.Model):
    __tablename__ = "restaurant_category"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="categories")
    products = db.relationship("RestaurantProduct", back_populates="category", passive_deletes=True)
    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "slug", name="uq_restaurant_category_slug"),
        db.Index("ix_restaurant_category_restaurant_active", "restaurant_id", "active"),
    )


class RestaurantProduct(db.Model):
    __tablename__ = "restaurant_product"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("restaurant_category.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(220), nullable=False)
    sku = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, default="")
    price_delivery = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price_pickup = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    image = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    featured = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="products")
    category = db.relationship("RestaurantCategory", back_populates="products")
    order_items = db.relationship("OrderItem", back_populates="restaurant_product")

    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "slug", name="uq_restaurant_product_slug"),
        db.UniqueConstraint("restaurant_id", "sku", name="uq_restaurant_product_sku"),
        db.Index("ix_restaurant_product_restaurant_active", "restaurant_id", "active"),
    )

    @property
    def available(self):
        return self.active and self.stock > 0

    @property
    def stock_label(self):
        if self.stock <= 0:
            return "Agotado"
        if self.stock <= 5:
            return "Últimas unidades"
        return "Disponible"


class RestaurantHour(db.Model):
    __tablename__ = "restaurant_hour"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday = db.Column(db.Integer, nullable=False)
    closed = db.Column(db.Boolean, default=False, nullable=False)
    start_time = db.Column(db.String(5), default="19:00")
    end_time = db.Column(db.String(5), default="00:00")
    start_time_2 = db.Column(db.String(5), default="")
    end_time_2 = db.Column(db.String(5), default="")

    restaurant = db.relationship("Restaurant", back_populates="hours")
    __table_args__ = (db.UniqueConstraint("restaurant_id", "weekday", name="uq_restaurant_hour_day"),)
