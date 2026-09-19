# MundoMix

E-commerce Flask de MundoMix. Esta versión no incorpora gastronomía.

## Arquitectura

- Flask + SQLAlchemy + PostgreSQL.
- Flask-Migrate/Alembic para cambios de esquema.
- Cloudinary como almacenamiento permanente de imágenes.
- Gunicorn para producción.

## Imágenes

Las imágenes de productos, imágenes adicionales, categorías y banners se almacenan en Cloudinary. PostgreSQL conserva `secure_url` y `cloudinary_public_id`; las adicionales mantienen compatibilidad mediante `additional_images` + `additional_image_public_ids`.

Variables obligatorias en producción:

```env
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

El secreto nunca debe aparecer en frontend, logs, Git ni `.env.example`.

## Migraciones

```bash
flask --app wsgi db heads
flask --app wsgi db history
flask --app wsgi db current
flask --app wsgi db upgrade
```

No usar `db.create_all()` ni `db.drop_all()` para evolucionar producción.

## Migrar imágenes existentes

Después de aplicar el esquema Cloudinary y configurar las credenciales, ejecutar:

```bash
python scripts/migrate_images_to_cloudinary.py
```

El proceso es repetible, no borra `uploads/` durante la primera etapa y muestra productos, categorías, banners, adicionales, ya migrados y errores.

## Desarrollo

```bash
pip install -r requirements.txt
python app.py
```

## Producción

```bash
flask --app wsgi db upgrade
gunicorn wsgi:app
```

Variables principales: `DATABASE_URL`, `SECRET_KEY`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.

## Funcionalidad conservada

Tienda, productos, categorías, banners, carrito, checkout, pedidos y administración. No se agregan restaurantes, menú, pedidos gastronómicos ni rutas de gastronomía.
