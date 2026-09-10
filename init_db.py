from app import create_app
from extensions import db
from models import Admin, Category, Product, Setting
from werkzeug.security import generate_password_hash
from slugify import make_slug

app=create_app()
with app.app_context():
    db.create_all()
    if not Admin.query.first():
        db.session.add(Admin(username="admin", password_hash=generate_password_hash("cambiar-esta-clave")))
    if not Category.query.first():
        for name in ["Tecnología","Hogar","Herramientas","Accesorios","Electrónica","Ofertas"]:
            db.session.add(Category(name=name, slug=make_slug(name)))
    defaults={
        "store_name":"MundoMix","whatsapp_number":"","description":"Comprá online en MundoMix.",
        "contact":"","social":"","pickup_address":"","business_hours":"","delivery_info":"Consultá disponibilidad de entrega."
    }
    for key,value in defaults.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key,value=value))
    db.session.commit()
    print("Base de datos inicializada.")
    print("Usuario admin: admin")
    print("Contraseña inicial: cambiar-esta-clave")
