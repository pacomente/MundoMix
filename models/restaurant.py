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
    info = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    accept_orders = db.Column(db.Boolean, default=True, nullable=False, index=True)
    accept_orders_closed = db.Column(db.Boolean, default=False, nullable=False)
    pause_message = db.Column(db.String(300), default="Estamos temporalmente pausados.")
    delivery_enabled = db.Column(db.Boolean, default=True, nullable=False)
    pickup_enabled = db.Column(db.Boolean, default=True, nullable=False)
    delivery_fee = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    minimum_order = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    delivery_zones = db.Column(db.JSON, default=list)
    prep_min = db.Column(db.Integer, default=20, nullable=False)
    prep_max = db.Column(db.Integer, default=30, nullable=False)
    theme_color = db.Column(db.String(20), default="#e21b23")
    print_settings = db.Column(db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    users = db.relationship("RestaurantUser", back_populates="restaurant", cascade="all, delete-orphan")
    categories = db.relationship("RestaurantCategory", back_populates="restaurant", cascade="all, delete-orphan", passive_deletes=True)
    products = db.relationship("RestaurantProduct", back_populates="restaurant", cascade="all, delete-orphan", passive_deletes=True)
    orders = db.relationship("Order", back_populates="restaurant")
    hours = db.relationship("RestaurantHour", back_populates="restaurant", cascade="all, delete-orphan", order_by="RestaurantHour.weekday")
    modifier_groups = db.relationship("ModifierGroup", back_populates="restaurant", cascade="all, delete-orphan", passive_deletes=True)
    promotions = db.relationship("RestaurantPromotion", back_populates="restaurant", cascade="all, delete-orphan", passive_deletes=True)


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
    __table_args__ = (db.UniqueConstraint("restaurant_id", "slug", name="uq_restaurant_category_slug"), db.Index("ix_restaurant_category_restaurant_active", "restaurant_id", "active"))


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
    previous_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    stock_control = db.Column(db.Boolean, default=False, nullable=False)
    image = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    featured = db.Column(db.Boolean, default=False, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    label = db.Column(db.String(40), default="")
    nutrition = db.Column(db.Text, default="")
    prep_min = db.Column(db.Integer, nullable=True)
    prep_max = db.Column(db.Integer, nullable=True)
    is_combo = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    restaurant = db.relationship("Restaurant", back_populates="products")
    category = db.relationship("RestaurantCategory", back_populates="products")
    order_items = db.relationship("OrderItem", back_populates="restaurant_product")
    modifier_links = db.relationship("ProductModifierGroup", back_populates="product", cascade="all, delete-orphan", passive_deletes=True, order_by="ProductModifierGroup.display_order")
    combo_components = db.relationship("ComboComponent", back_populates="combo", cascade="all, delete-orphan", foreign_keys="ComboComponent.combo_id", passive_deletes=True)
    @property
    def available(self):
        return self.active and (not self.stock_control or self.stock > 0)
    @property
    def stock_label(self):
        if self.stock_control and self.stock <= 0:
            return "Agotado"
        if self.stock_control and self.stock <= 5:
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


class ModifierGroup(db.Model):
    __tablename__ = "modifier_group"
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    min_choices = db.Column(db.Integer, default=0, nullable=False)
    max_choices = db.Column(db.Integer, default=1, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    restaurant = db.relationship("Restaurant", back_populates="modifier_groups")
    options = db.relationship("ModifierOption", back_populates="group", cascade="all, delete-orphan", order_by="ModifierOption.display_order")
    product_links = db.relationship("ProductModifierGroup", back_populates="group", cascade="all, delete-orphan", passive_deletes=True)


class ModifierOption(db.Model):
    __tablename__ = "modifier_option"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("modifier_group.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    price_delta = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    group = db.relationship("ModifierGroup", back_populates="options")


class ProductModifierGroup(db.Model):
    __tablename__ = "product_modifier_group"
    product_id = db.Column(db.Integer, db.ForeignKey("restaurant_product.id", ondelete="CASCADE"), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("modifier_group.id", ondelete="CASCADE"), primary_key=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    product = db.relationship("RestaurantProduct", back_populates="modifier_links")
    group = db.relationship("ModifierGroup", back_populates="product_links")


class ComboComponent(db.Model):
    __tablename__ = "combo_component"
    id = db.Column(db.Integer, primary_key=True)
    combo_id = db.Column(db.Integer, db.ForeignKey("restaurant_product.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("restaurant_product.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    combo = db.relationship("RestaurantProduct", foreign_keys=[combo_id], back_populates="combo_components")
    product = db.relationship("RestaurantProduct", foreign_keys=[product_id])


class RestaurantPromotion(db.Model):
    __tablename__ = "restaurant_promotion"
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    promotion_type = db.Column(db.String(20), nullable=False, default="percentage")
    value = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("restaurant_product.id", ondelete="CASCADE"), nullable=True, index=True)
    min_quantity = db.Column(db.Integer, default=2, nullable=False)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    restaurant = db.relationship("Restaurant", back_populates="promotions")
    product = db.relationship("RestaurantProduct")
