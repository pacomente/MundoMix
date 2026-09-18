# MUNDOMIX — Auditoría y migración integral de imágenes a Cloudinary

## Base auditada
`MundoMix_gastronomia_2_0_desde_auditado(1).zip`

## Resultado
Se implementó una capa central de Cloudinary y una migración de esquema no destructiva. Las columnas legacy (`image`, `additional_images`, `logo`, `banner`) se conservan para compatibilidad y migración; las imágenes nuevas se guardan directamente en Cloudinary y PostgreSQL conserva URL optimizada + `public_id`.

## A. Auditoría anterior

Se encontraron referencias de imágenes en:
- `Product.image` y `Product.additional_images`.
- `Category.image`.
- `Banner.image`.
- `Restaurant.logo` y `Restaurant.banner`.
- `RestaurantProduct.image`.
- `/uploads/<path:filename>` y `UPLOAD_FOLDER` como mecanismo legacy.
- Subidas mediante `request.files` y guardado local en `routes/admin.py` y `routes/restaurant_panel.py`.
- Templates públicos y paneles que utilizaban `uploaded_file`.

No se encontraron `BYTEA`, `LargeBinary`, BLOB ni imágenes binarias almacenadas directamente en PostgreSQL.

En el ZIP auditado no había archivos de imagen reales dentro de `uploads/`; solamente `.gitkeep`.

## B. Arquitectura nueva

```text
Formulario → Flask → validación Pillow → Cloudinary → secure_url + public_id → PostgreSQL
```

Servicio central:
`services/cloudinary_service.py`

Funciones principales:
- `upload_image()`
- `delete_image()`
- `generate_url()`
- `validate_image()`
- utilidades legacy para migración

Las nuevas URLs se generan HTTPS con `quality=auto` y `fetch_format=auto`.

## C. Modelos modificados

- `models/product.py`
  - `image_url`
  - `cloudinary_public_id`
  - `additional_image_urls`
  - `additional_image_public_ids`
- `models/category.py`
  - `image_url`
  - `cloudinary_public_id`
- `models/banner.py`
  - `image_url`
  - `cloudinary_public_id`
- `models/restaurant.py`
  - `logo_url`
  - `logo_cloudinary_public_id`
  - `banner_url`
  - `banner_cloudinary_public_id`
- `models/restaurant.py / RestaurantProduct`
  - `image_url`
  - `cloudinary_public_id`

No se crearon modelos duplicados.

## D. Migración Alembic

Nueva migración:
`20260918_04_cloudinary.py`

Cadena:

```text
20260915_01
  ↓
20260915_02_gastronomia_20
  ↓
20260915_03_printing
  ↓
20260918_04_cloudinary
```

No se creó una rama adicional.

La migración es incremental y todas las columnas nuevas son `nullable=True` para no romper registros existentes.

No modifica manualmente `alembic_version`.

## E. Imágenes migradas

La ejecución real contra Cloudinary/PostgreSQL de producción no fue posible en este entorno porque no hay credenciales Cloudinary, acceso a la base PostgreSQL de producción ni red de salida.

Conteo local del ZIP base:

```text
Productos:                 no ejecutado contra DB
Categorías:                no ejecutado contra DB
Banners:                   no ejecutado contra DB
Restaurantes:              no ejecutado contra DB
Productos gastronómicos:   no ejecutado contra DB
Otros:                     no ejecutado contra DB
Archivos legacy locales:   0 imágenes reales encontradas en uploads/
```

Script disponible:
`scripts/migrate_images_to_cloudinary.py`

Es repetible, no elimina archivos legacy, continúa después de errores y muestra encontradas/migradas/ya migradas/fallidas.

## F. Errores

No se produjeron errores de migración porque la migración remota no se ejecutó sin credenciales. El script registra los errores de cada recurso y continúa con el resto cuando se ejecute en el entorno con acceso real.

## G. Carpetas Cloudinary

```text
mundomix/products
mundomix/categories
mundomix/banners
mundomix/restaurants/{restaurant_id}/logo
mundomix/restaurants/{restaurant_id}/banner
mundomix/restaurants/{restaurant_id}/products
```

## H. PostgreSQL

La migración añade referencias para:
- Product
- Category
- Banner
- Restaurant
- RestaurantProduct

Las columnas legacy se mantienen deliberadamente hasta completar la verificación de producción.

## I. Alembic

Resultado estático del árbol de migraciones: una única head esperada, `20260918_04_cloudinary`.

Los comandos reales:

```text
flask db heads
flask db current
flask db history
flask db upgrade
```

no pudieron ejecutarse aquí porque el entorno de ejecución suministrado no contiene Flask/Flask-Migrate ni una PostgreSQL conectada.

## J. Tests ejecutados

- Python `compileall`: PASS.
- Parseo de todas las plantillas Jinja: PASS, 0 errores.
- HTML: eliminación de formularios anidados existentes en carrito gastronómico: PASS, 0 formularios anidados.
- Validación Pillow de JPEG válido: PASS.
- Archivo disfrazado de imagen: rechazado correctamente.
- Extensión no permitida: rechazada correctamente.
- Búsqueda de `.save()` de archivos de imagen en rutas: 0 usos.
- `db.drop_all()`: no encontrado.
- `Base.metadata.drop_all()`: no encontrado.
- ZIP final: se verificará con `unzip -t`.

No se afirmó como probado lo que requiere servicios externos: Cloudinary real, PostgreSQL real, Render, WhatsApp o una impresora física.

## K. Git

El ZIP base no contiene un checkout Git operativo (`.git` no está disponible en el entorno de trabajo), por lo que no fue posible ejecutar de forma real:

```text
git status
git diff
git branch --show-current
git commit
git push
```

No se incluyen `.env` ni credenciales Cloudinary.

## L. Render

La aplicación queda preparada para producción con:
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `DATABASE_URL`

En producción, si falta alguna credencial Cloudinary, el arranque falla explícitamente en lugar de iniciar con un sistema de almacenamiento de imágenes incompleto.

`/health` y `/.well-known/appspecific/com.chrome.devtools.json` se conservan.

## Seguridad y datos

- No se usa `db.drop_all()`.
- No se eliminan tablas existentes.
- No se eliminan columnas legacy en esta etapa.
- No se borran imágenes legacy durante la migración automática.
- Los nuevos archivos nunca se guardan en `uploads/`.
- El API secret de Cloudinary solo se utiliza en backend.
- Los templates consumen URLs HTTPS de Cloudinary cuando existen y solo utilizan el endpoint `/uploads` como fallback legacy.
