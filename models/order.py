from datetime import datetime
from extensions import db

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(160), nullable=False)
    customer_phone = db.Column(db.String(40), nullable=False)
    fulfillment_method = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(300), default="")
    notes = db.Column(db.Text, default="")
    total = db.Column(db.Numeric(12,2), nullable=False)
    status = db.Column(db.String(30), default="Nuevo", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    product_name_snapshot = db.Column(db.String(180), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12,2), nullable=False)
    subtotal = db.Column(db.Numeric(12,2), nullable=False)
    order = db.relationship("Order", back_populates="items")
