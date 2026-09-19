from __future__ import annotations

import json
from datetime import datetime

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
    # Kept as `image` for compatibility; it now contains Cloudinary secure_url.
    image = db.Column(db.String(1000))
    cloudinary_public_id = db.Column(db.String(255))
    # JSON arrays: [{"url": "...", "public_id": "..."}, ...]
    additional_images = db.Column(db.Text, default="")
    featured = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    category = db.relationship("Category", back_populates="products")

    @property
    def additional_image_assets(self):
        raw = self.additional_images or ""
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                assets = []
                for item in data:
                    if isinstance(item, dict) and item.get("url"):
                        assets.append({"url": item["url"], "public_id": item.get("public_id")})
                    elif isinstance(item, str) and item:
                        assets.append({"url": item, "public_id": None})
                return assets
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        # Legacy format: comma-separated local paths/URLs.
        return [{"url": x.strip(), "public_id": None} for x in raw.split(",") if x.strip()]

    @property
    def image_list(self):
        return [asset["url"] for asset in self.additional_image_assets]

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
        return "Disponible"

    def set_additional_image_assets(self, assets):
        self.additional_images = json.dumps(assets, ensure_ascii=False, separators=(",", ":")) if assets else ""
