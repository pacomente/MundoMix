from datetime import datetime
import json
from extensions import db


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    sku = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    price_delivery = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price_pickup = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True, index=True)
    image = db.Column(db.String(500))
    cloudinary_public_id = db.Column(db.String(255))
    additional_images = db.Column(db.Text, default="")
    additional_image_public_ids = db.Column(db.Text, default="")
    featured = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    category = db.relationship("Category", back_populates="products")

    @property
    def image_list(self):
        return [x for x in (self.additional_images or "").split(",") if x]

    @property
    def additional_public_id_list(self):
        try:
            value = json.loads(self.additional_image_public_ids or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def all_images(self):
        return ([self.image] if self.image else []) + self.image_list

    @property
    def available(self):
        return self.active and self.stock > 0

    @property
    def stock_label(self):
        if self.stock <= 0:
            return "Agotado"
        if self.stock <= 5:
            return "Últimas unidades"
        return "En stock"
