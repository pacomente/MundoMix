import os

from app import create_app
from flask_migrate import upgrade
from extensions import db
from models import Admin, Category, Setting
from slugify import make_slug
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    # Schema creation/evolution belongs to Flask-Migrate/Alembic.
    upgrade(directory="migrations")

    if not Admin.query.first():
        initial_password = os.getenv("ADMIN_INITIAL_PASSWORD", "").strip()
        if not initial_password:
            raise RuntimeError(
                "ADMIN_INITIAL_PASSWORD es obligatoria para crear el primer administrador. "
                "Configurala en .env o en el entorno y volvé a ejecutar init_db.py."
            )
        db.session.add(
            Admin(username="admin", password_hash=generate_password_hash(initial_password))
        )

    if not Category.query.first():
        for name in ["Tecnología", "Hogar", "Herramientas", "Accesorios", "Electrónica", "Ofertas"]:
            db.session.add(Category(name=name, slug=make_slug(name)))

    defaults = {
        "store_name": "MundoMix",
        "whatsapp_number": "",
        "description": "Comprá online en MundoMix.",
        "contact": "",
        "social": "",
        "pickup_address": "",
        "business_hours": "",
        "delivery_info": "Consultá disponibilidad de entrega.",
    }
    for key, value in defaults.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=value))

    db.session.commit()
    print("Base de datos inicializada mediante Flask-Migrate/Alembic.")
    print("Usuario admin: admin")
