# MundoMix — E-commerce + PostgreSQL + Cloudinary

MundoMix es una tienda online desarrollada con **Python + Flask + SQLAlchemy + Jinja2 + HTML/CSS/JavaScript**.

La versión actual conserva la tienda general y su lógica comercial, pero migra el almacenamiento permanente de imágenes a **Cloudinary**. No incluye gastronomía, restaurantes ni modelos/rutas gastronómicas.

## Arquitectura

```text
Cliente
  ↓
Flask
  ├── SQLAlchemy → PostgreSQL
  └── Cloudinary Service → Cloudinary
```

PostgreSQL conserva los datos de negocio y las referencias de imágenes. Cloudinary conserva los archivos de imagen.

## Funcionalidades conservadas

- Homepage responsive con banners.
- Catálogo con búsqueda, filtros, ordenamiento y paginación.
- Productos y categorías.
- Carrito.
- Checkout y pedidos.
- WhatsApp configurable.
- Dos precios finales por producto: envío incluido y retiro.
- Stock descontado al confirmar un pedido.
- Panel administrativo.
- Productos, categorías, banners, pedidos y configuración.
- Login con hash de contraseñas.
- `/health` y endpoint de Chrome DevTools.

## Imágenes con Cloudinary

Todas las imágenes permanentes de MundoMix se gestionan mediante:

```text
mundomix/products/
mundomix/categories/
mundomix/banners/
```

El backend utiliza `services/cloudinary_service.py` para validar, subir, reemplazar, eliminar y construir URLs de imagen.

Los modelos conservan `image` por compatibilidad, pero ahora contiene la `secure_url` de Cloudinary. Además almacenan `cloudinary_public_id`. Las imágenes adicionales de productos se guardan como JSON con `url` y `public_id`.

### Variables obligatorias en producción

```env
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

El secreto nunca se envía al navegador ni se incluye en `.env.example` con un valor real.

## Validación de imágenes

Se aceptan únicamente:

```text
JPG / JPEG / PNG / WEBP
```

Se valida extensión, MIME cuando está disponible, contenido real mediante Pillow, corrupción y tamaño. El límite de la petición es 8 MB.

## Migrar imágenes locales existentes

Si todavía existen imágenes heredadas en `uploads/`, primero actualizar el esquema:

```bash
flask --app wsgi db upgrade
```

Luego configurar Cloudinary y ejecutar:

```bash
python scripts/migrate_images_to_cloudinary.py
```

Para comprobar antes de modificar la base:

```bash
python scripts/migrate_images_to_cloudinary.py --dry-run
```

El script es repetible, conserva los archivos locales y muestra:

```text
Encontradas/validadas
Migradas
Ya migradas
Errores
```

No elimina archivos locales automáticamente.

## Base de datos y Alembic

Los cambios de esquema se realizan mediante Flask-Migrate/Alembic.

```bash
flask --app wsgi db heads
flask --app wsgi db history
flask --app wsgi db current
flask --app wsgi db upgrade
```

No usar `db.create_all()` para actualizar producción y nunca usar `db.drop_all()` para desplegar cambios.

La migración inicial `20260919_01` es conservadora: en una base nueva crea el esquema; si las tablas ya existen, agrega únicamente las columnas necesarias para Cloudinary y la protección de stock.

No editar manualmente `alembic_version`.

## SQLite → PostgreSQL

El script existente continúa preservando la SQLite y los IDs. Antes de ejecutarlo, el PostgreSQL destino debe tener el esquema aplicado mediante Alembic:

```bash
flask --app wsgi db upgrade
python scripts/migrate_sqlite_to_postgres.py
```

El script **no usa `db.create_all()`** y se detiene si faltan tablas en el destino.

## Desarrollo local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copiar `.env.example` a `.env` y configurar una `SECRET_KEY`. Para utilizar uploads administrativos también deben estar configuradas las credenciales de Cloudinary.

Inicializar una base nueva:

```cmd
set ADMIN_INITIAL_PASSWORD=una-clave-segura
python init_db.py
python app.py
```

`init_db.py` ejecuta Alembic y luego crea el administrador/configuración inicial. No crea tablas mediante `db.create_all()`.

## Producción / Render

Variables:

```env
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=...
DATABASE_URL=postgresql+psycopg://...
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
WHATSAPP_NUMBER=...
SESSION_COOKIE_SECURE=1
```

El proceso recomendado es:

```bash
flask --app wsgi db upgrade
gunicorn wsgi:app
```

Render no se utiliza como almacenamiento permanente de imágenes. Reiniciar o redeployar la aplicación no afecta los assets de Cloudinary.

## Health check

```text
GET /health
```

PostgreSQL operativo:

```json
{"status":"ok"}
```

HTTP 200. Si PostgreSQL no responde, devuelve HTTP 503 sin exponer credenciales.

## Seguridad

- No se guardan secretos de Cloudinary en el código.
- No se envía `CLOUDINARY_API_SECRET` al frontend.
- Las operaciones de administración requieren sesión de administrador.
- Las URLs `next` del login se restringen a rutas internas.
- Los uploads se validan mediante Pillow.
- No se permite path traversal para imágenes.
- Las transacciones SQL se revierten ante errores.
- El error 500 hace rollback antes de renderizar para evitar errores secundarios de PostgreSQL.

## Sin gastronomía

Esta versión no contiene funcionalidades de:

```text
Restaurant
RestaurantUser
RestaurantProduct
RestaurantCategory
RestaurantOrder
RestaurantOrderItem
RestaurantSettings
/comida
```

El proyecto se limita al ecommerce general de MundoMix.
