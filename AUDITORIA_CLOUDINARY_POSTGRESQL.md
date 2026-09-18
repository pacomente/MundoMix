# MundoMix — Auditoría y actualización Cloudinary + PostgreSQL

## Base

Se trabajó sobre `MundoMix_gastronomia_3_0_final(1).zip`, preservando la arquitectura existente. La actualización agrega una capa centralizada de Cloudinary y corrige la recuperación de transacciones PostgreSQL sin usar `drop_all()` ni borrar datos.

## Error PostgreSQL

El código actual tenía un context processor que consultaba `Setting.query.all()` sin recuperación. Si una consulta anterior había abortado la transacción PostgreSQL, esa consulta secundaria producía `InFailedSqlTransaction` y podía interferir con el renderizado del error.

Se corrigió:

- `app.py`: `inject_globals()` ahora captura la falla de `Setting.query.all()`, registra la excepción, ejecuta rollback seguro y devuelve configuraciones vacías como default.
- `app.py`: el `errorhandler(500)` registra primero la excepción original, hace rollback seguro y tiene un fallback de texto si incluso el template de error falla.
- No se oculta la excepción original en logs.

**Limitación:** no hay logs de Render ni credenciales de producción en este entorno, por lo que no es posible afirmar cuál fue la primera sentencia SQL que abortó la transacción en producción. La reparación del mecanismo secundario está implementada; la causa primaria debe confirmarse con el log de Render inmediatamente anterior a `InFailedSqlTransaction`.

## Cloudinary

Servicio central: `services/cloudinary_service.py`.

Responsabilidades:

- validación de extensión, MIME, tamaño y contenido real con Pillow;
- JPG/JPEG, PNG y WEBP;
- máximo 8 MB;
- upload a Cloudinary con URL HTTPS segura;
- `public_id` persistido;
- calidad/formato automáticos de Cloudinary;
- eliminación con invalidación;
- errores explícitos.

### Referencias agregadas

| Modelo | Campo de URL existente | Referencia Cloudinary |
|---|---|---|
| Product | `image` | `cloudinary_public_id` |
| Product | `additional_images` | `additional_image_public_ids` |
| Category | `image` | `cloudinary_public_id` |
| Banner | `image` | `cloudinary_public_id` |
| Restaurant | `logo` | `logo_cloudinary_public_id` |
| Restaurant | `banner` | `banner_cloudinary_public_id` |
| RestaurantProduct | `image` | `cloudinary_public_id` |

Los campos antiguos no fueron eliminados para preservar imágenes legacy.

## Reemplazo y rollback

La secuencia de reemplazo es:

1. subir nueva imagen;
2. guardar URL/public_id en SQLAlchemy;
3. hacer commit;
4. eliminar la imagen Cloudinary anterior.

Si falla el commit, se hace rollback y se intenta eliminar la nueva imagen subida. Si falla la eliminación posterior de la imagen anterior, la DB conserva la referencia nueva y el error queda registrado para limpieza posterior.

## Imágenes existentes

No se ejecutó una migración contra PostgreSQL de producción porque no se proporcionaron sus credenciales ni acceso de red. El ZIP local no contiene imágenes reales dentro de `uploads` más allá de placeholders `.gitkeep`.

Se incorporó `scripts/migrate_images_to_cloudinary.py` para ejecutar la migración real de forma segura en el entorno con acceso a la DB y Cloudinary. No elimina archivos legacy.

## Migración DB

Nueva migración:

`migrations/versions/20260918_04_cloudinary.py`

Base: `20260915_03_printing`.

No elimina tablas, columnas ni datos. Agrega solamente referencias nullable para Cloudinary.

## Aislamiento gastronómico

Los uploads gastronómicos siguen pasando por rutas protegidas por `restaurant_required` y las consultas de productos/configuración mantienen el `restaurant_id`. Cloudinary no recibe autorización desde el frontend: el backend decide el folder y la referencia que se puede modificar.

## Compatibilidad de frontend

Se agregó `image_src()` como helper Jinja:

- URL `http://`/`https://` → se sirve directamente;
- ruta legacy → se resuelve mediante `/uploads/...`.

Así las imágenes antiguas siguen visibles mientras las nuevas usan Cloudinary. Las plantillas ya no construyen manualmente URLs `/uploads` para las imágenes.

## Pruebas ejecutadas en este entorno

| Prueba | Resultado |
|---|---|
| Compilación Python (`compileall`) | PASS |
| Parseo de todas las plantillas Jinja | PASS (0 errores) |
| Cadena de migraciones revisada estáticamente | PASS |
| Referencias de modelos a `cloudinary_public_id` | PASS |
| Nuevos uploads no usan `file.save()` | PASS |
| Plantillas sin `url_for('uploaded_file', ...)` | PASS |
| Validación de sintaxis del servicio Cloudinary | PASS |
| PostgreSQL real | NO EJECUTABLE: sin DB de producción |
| Upload real a Cloudinary | NO EJECUTABLE: sin credenciales/red |
| Restart/redeploy de Render | NO EJECUTABLE: sin acceso al servicio |
| DevTools Network real | NO EJECUTABLE: sin navegador contra producción |
| E2E completo | NO EJECUTABLE en este entorno |

## Archivos modificados/agregados

- `app.py`
- `config.py`
- `.env.example`
- `requirements.txt`
- `models/product.py`
- `models/category.py`
- `models/banner.py`
- `models/restaurant.py`
- `routes/admin.py`
- `routes/restaurant_panel.py`
- `services/__init__.py`
- `services/cloudinary_service.py`
- `scripts/migrate_images_to_cloudinary.py`
- `migrations/versions/20260918_04_cloudinary.py`
- plantillas HTML que mostraban imágenes
- `README.md`
- `AUDITORIA_CLOUDINARY_POSTGRESQL.md`

## Pendientes de producción

1. Configurar en Render `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` y `CLOUDINARY_API_SECRET`.
2. Ejecutar `flask db upgrade` en el PostgreSQL de producción después de verificar el head actual.
3. Ejecutar `python scripts/migrate_images_to_cloudinary.py` con acceso a la DB de producción.
4. Revisar el resultado y conservar los archivos legacy hasta verificar todas las URLs.
5. Probar un upload, reemplazo, eliminación y persistencia después de restart/redeploy.
6. Revisar los logs de Render para identificar la primera consulta SQL que precedió a `InFailedSqlTransaction`.

**Importante:** no se declaró PASS ninguna prueba que requiera servicios externos no disponibles en este entorno.
