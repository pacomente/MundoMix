# MundoMix — Auditoría y reparación Cloudinary

## Base auditada

El entorno proporcionó como archivo disponible `MundoMix_checkout_corregido(1).zip`. No existe un archivo `MundoMix_checkout_corregido(2).zip` en el filesystem de ejecución. Por trazabilidad, los cambios de esta entrega se hicieron sobre el archivo disponible indicado arriba y no sobre una base inventada.

## Hallazgos principales de la base

### Críticos / altos

1. Las imágenes se guardaban en `uploads/` mediante `file.save()` y se servían con `/uploads/<path:filename>`.
2. `db.create_all()` se ejecutaba automáticamente en desarrollo y `init_db.py` lo utilizaba como mecanismo de creación de esquema.
3. No había un árbol de migraciones Alembic en la base recibida.
4. `requirements.txt` no incluía el SDK oficial de Cloudinary.
5. El modelo no tenía `cloudinary_public_id` para producto, categoría ni banner.
6. `additional_images` almacenaba rutas locales separadas por comas, sin `public_id`.
7. Editar un producto reemplazaba la lista de imágenes adicionales en vez de conservar las existentes.
8. Crear una categoría no permitía cargar imagen desde el formulario.
9. El contexto global consultaba `Setting` sin protección frente a una transacción PostgreSQL abortada.
10. El error 500 podía intentar renderizar una plantilla mientras la sesión SQLAlchemy seguía abortada.
11. El login aceptaba un `next` sin validación explícita de ruta interna.
12. El flujo de confirmación de pedidos podía volver a descontar stock después de una transición posterior y una nueva confirmación, porque no existía un indicador persistente de descuento.
13. El carrito convertía IDs de sesión sin manejo de valores corruptos.

### Medios

- Documentación y configuración estaban orientadas a almacenamiento permanente en `uploads/`.
- Las plantillas dependían directamente del endpoint `uploaded_file`.
- No había proceso repetible para migrar imágenes antiguas.
- No había optimización centralizada de URLs de imagen.

## Reparaciones

- Servicio central `services/cloudinary_service.py`.
- Validación Pillow + extensión + MIME + tamaño.
- Carpetas Cloudinary `mundomix/products`, `mundomix/categories`, `mundomix/banners`.
- URLs seguras + `cloudinary_public_id` en PostgreSQL.
- JSON de assets para imágenes adicionales.
- Upload/reemplazo/eliminación centralizados.
- Limpieza compensatoria de nuevos assets cuando falla la transacción.
- URLs de entrega mediante transformaciones `quality=auto`, `fetch_format=auto` y límites de tamaño.
- Migración repetible `scripts/migrate_images_to_cloudinary.py`.
- Retiro de `/uploads/`, `UPLOAD_FOLDER`, `save_image()` y `send_from_directory()` del código activo.
- `init_db.py` ahora ejecuta Alembic.
- `scripts/migrate_sqlite_to_postgres.py` ya no usa `db.metadata.create_all()`.
- Context processor y error 500 con rollback defensivo.
- Validación de `next` como ruta interna.
- Protección persistente contra doble descuento de stock mediante `Order.stock_deducted`.
- Manejo de valores corruptos en carrito.
- README y `.env.example` actualizados.

## Migración Alembic

Se creó una migración única:

```text
20260919_01_initial_cloudinary
```

La migración crea el esquema en una base nueva y, si las tablas ya existen, agrega las columnas Cloudinary y la protección de stock necesarias. No modifica manualmente `alembic_version` y no utiliza `drop_all()`.

No fue posible ejecutar los comandos reales de Flask-Migrate porque el entorno de ejecución no tenía Flask/Flask-Migrate/psycopg instalados y no tiene acceso a Internet para instalarlos.

## Pruebas ejecutadas en este entorno

- `python -m compileall .` → **OK**.
- 22 templates Jinja analizados → **0 errores de sintaxis**.
- Referencias `url_for()` contra endpoints definidos → **0 endpoints faltantes**.
- `node --check static/js/main.js` → **OK**.
- Validación de una imagen PNG real mediante Pillow → **OK**.
- Archivo corrupto rechazado por Pillow → **OK**.
- Búsqueda de dependencias activas de `uploaded_file`, `/uploads/`, `UPLOAD_FOLDER`, `save_image()` y `send_from_directory()` → **0 coincidencias activas**.
- Búsqueda de gastronomía en `.py`, `.html` y `.js` → **0 coincidencias funcionales**.

## Pruebas que requieren servicios externos y NO se declararon como ejecutadas

- Cloudinary real.
- PostgreSQL real.
- `flask db heads/history/current/upgrade` real.
- Upload/delete real en Cloudinary.
- Migración real de imágenes de producción.
- Render.
- Git commit/push.
- Flujo HTTP completo con navegador.

No se inventaron resultados para esas pruebas.
