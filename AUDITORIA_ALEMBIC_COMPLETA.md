# MundoMix — Auditoría completa y reparación definitiva de Alembic

## 1. Error original

El problema real no era la existencia de dos ramas válidas que requirieran `flask db merge heads`. La migración `20260915_01_restaurants.py` declara como ID real:

```python
revision = "20260915_01"
```

pero `20260915_02_gastronomia_20.py` apuntaba a:

```python
down_revision = "20260915_01_restaurants"
```

Ese ID no existe. Por lo tanto, la cadena quedaba referenciando un padre inexistente y Alembic no podía construir correctamente el grafo.

## 2. Árbol anterior

```text
20260915_01

20260915_01_restaurants  <-- referencia inexistente
    ↓
20260915_02_gastronomia_20
    ↓
20260915_03_printing
    ↓
20260918_04_cloudinary
```

El análisis estático del grafo produjo dos heads aparentes porque `20260915_02_gastronomia_20` estaba desconectada de la raíz.

## 3. Corrección

Se corrigió únicamente el `down_revision` de `20260915_02_gastronomia_20`:

```python
down_revision = "20260915_01"
```

No se creó un merge porque no había dos heads válidas que unificar.

## 4. Árbol final

```text
20260915_01
    ↓
20260915_02_gastronomia_20
    ↓
20260915_03_printing
    ↓
20260918_04_cloudinary
    ↓
20260918_05_schema_indexes
```

Resultado del análisis estático: **1 root, 1 head, 0 padres inexistentes**.

## 5. Reparación adicional del historial

La raíz histórica `20260915_01` originalmente dependía de que las tablas core hubieran sido creadas previamente con `db.create_all()`. Eso impedía construir una PostgreSQL vacía únicamente mediante Alembic. Se reforzó la migración raíz para crear, cuando no existen, las tablas core de MundoMix (`category`, `admin`, `banner`, `setting`, `product`, `order`, `order_item`) antes de aplicar la capa gastronómica. Las tablas existentes no se recrean.

También se adaptaron las alteraciones con foreign keys/nullable para que las migraciones sean compatibles con SQLite local mediante `batch_alter_table`.

## 6. Nueva migración de índices

Se añadió:

```text
20260918_05_schema_indexes.py
```

para alinear índices que los modelos declaraban y el historial no cubría de forma completa: `restaurant.accept_orders`, índice compuesto de `restaurant_category`, `order.scheduled_for`, `order.printed_at` y `restaurant_promotion.active`. Es idempotente y no elimina datos.

## 7. Cloudinary

Se auditó la implementación Cloudinary existente. El SDK está declarado en `requirements.txt` y el servicio central está en:

```text
services/cloudinary_service.py
```

Los modelos con referencias Cloudinary son:

- `Product`: `image_url`, `cloudinary_public_id`, `additional_image_urls`, `additional_image_public_ids`.
- `Category`: `image_url`, `cloudinary_public_id`.
- `Banner`: `image_url`, `cloudinary_public_id`.
- `Restaurant`: `logo_url`, `logo_cloudinary_public_id`, `banner_url`, `banner_cloudinary_public_id`.
- `RestaurantProduct`: `image_url`, `cloudinary_public_id`.

`RestaurantCategory` no posee campo de imagen en el modelo actual, por lo que no se inventó una columna/funcionalidad duplicada.

La búsqueda final no encontró `file.save()` en las rutas de administración. El endpoint `/uploads/<path:filename>` se conserva solamente para leer referencias legacy durante la transición.

## 8. PostgreSQL y transacciones

`app.py` ya no ejecuta `db.create_all()` en el arranque. `init_db.py` fue cambiado para ejecutar Alembic y luego sembrar datos. El script SQLite→PostgreSQL ya no crea el esquema con `metadata.create_all()`; exige que previamente se haya ejecutado `flask db upgrade`.

El error handler 500 hace `db.session.rollback()` antes de renderizar. El context processor de `Setting` también captura errores SQLAlchemy, hace rollback y usa un conjunto vacío de settings en lugar de realizar consultas sobre una transacción abortada.

## 9. Migración de imágenes existentes

No se ejecutó una migración real contra Cloudinary porque el entorno no contiene credenciales de producción ni acceso al PostgreSQL/Cloudinary del usuario. El script administrativo `scripts/migrate_images_to_cloudinary.py` queda separado del arranque de Flask y está diseñado para recorrer los modelos existentes, continuar ante fallos y reportar resultados.

Por lo tanto, en este entorno los contadores reales son:

```text
Productos: no ejecutado
Categorías: no ejecutado
Banners: no ejecutado
Restaurantes: no ejecutado
Productos gastronómicos: no ejecutado
Otros: no ejecutado
Total migrado: no ejecutado
```

No se afirma que una imagen haya sido migrada cuando no se pudo acceder a Cloudinary.

## 10. Pruebas realizadas

- `python -m compileall -q .`: **PASS**.
- Parseo de 44 templates Jinja: **PASS, 0 errores**.
- `node --check static/js/main.js`: **PASS**.
- Pillow: validación de PNG real y rechazo de archivo disfrazado: **PASS**.
- Grafo Alembic por AST: **PASS, 1 root / 1 head / 0 missing parents**.
- Las cinco migraciones `upgrade()` se ejecutaron sobre SQLite de prueba: **PASS**.
- Las cinco migraciones se ejecutaron nuevamente sobre el mismo esquema: **PASS**.
- Búsqueda de `db.create_all`, `metadata.create_all`, `drop_all` en Python: **0 coincidencias**.
- Búsqueda de escrituras locales de imágenes: **sin `file.save()`**.

La prueba SQLite valida la estructura y compatibilidad local de las migraciones; **no sustituye una prueba real contra PostgreSQL**.

## 11. Comandos que deben ejecutarse en el entorno real

Una vez instaladas las dependencias y configuradas las variables de entorno: `DATABASE_URL`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` y `CLOUDINARY_API_SECRET`, ejecutar:

```bash
flask --app wsgi:app db heads
flask --app wsgi:app db branches
flask --app wsgi:app db history
flask --app wsgi:app db current
flask --app wsgi:app db upgrade
```

Después, con PostgreSQL, verificar `alembic_version` mediante una consulta normal. No modificarla manualmente.

Luego ejecutar la migración administrativa de imágenes:

```bash
python scripts/migrate_images_to_cloudinary.py
```

## 12. Git / main

El ZIP recibido **no contiene `.git`**. Por lo tanto no es técnicamente posible verificar desde este entorno:

```text
git status
git diff
git branch --show-current
git log
git push origin main
```

No se realizó commit ni push y no se inventa que la rama sea `main`. El código queda listo para copiar al repositorio Git real, revisar el diff y ejecutar el commit/push allí.

## 13. Render

La configuración mantiene PostgreSQL vía `DATABASE_URL`, Gunicorn, health check `/health` y las variables de Cloudinary. No se puede confirmar un deploy real de Render desde este entorno. Antes del deploy real debe ejecutarse `flask db upgrade` sobre una base de staging y luego la migración de imágenes.
