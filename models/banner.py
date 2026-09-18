from extensions import db
class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), default="")
    subtitle = db.Column(db.String(300), default="")
    image = db.Column(db.String(255))
    image_url = db.Column(db.String(1000))
    cloudinary_public_id = db.Column(db.String(255), index=True)
    button_text = db.Column(db.String(80), default="")
    button_url = db.Column(db.String(300), default="")
    active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
