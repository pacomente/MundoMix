from extensions import db
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    slug = db.Column(db.String(140), nullable=False, unique=True)
    description = db.Column(db.Text, default="")
    image = db.Column(db.String(255))
    image_url = db.Column(db.String(1000))
    cloudinary_public_id = db.Column(db.String(255), index=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    products = db.relationship("Product", back_populates="category", passive_deletes=True)
