# MundoMix — Auditoría integral y reparación gastronómica

**Base auditada:** `MundoMix_marketplace_comida_auditado(1).zip`

**Objetivo:** estabilizar la implementación existente sin reconstruirla, sin `drop_all()`, sin borrar datos y sin agregar funcionalidades gastronómicas nuevas.

## 1. Diagnóstico del sistema encontrado

### Flujo cliente

```text
/comida
  -> /comida/<slug>
  -> /<slug>/carrito/*
  -> /comida/<slug>/checkout
  -> Order + OrderItem
  -> WhatsApp del Restaurant
```

### Flujo comercio

```text
/comercio/login
  -> /comercio/panel
  -> pedidos
  -> productos
  -> categorías
  -> configuración
```

### Flujo Super Admin

```text
/admin/login
  -> /admin
  -> locales
  -> productos/categorías/pedidos
```

Los modelos gastronómicos actuales son `Restaurant`, `RestaurantUser`, `RestaurantCategory`, `RestaurantProduct` y `RestaurantHour`. Los pedidos gastronómicos reutilizan `Order`/`OrderItem` mediante `restaurant_id` y `restaurant_product_id`.

## 2. Errores reales corregidos

### Error 1 — Formularios HTML anidados en el panel del comercio

- **Causa:** `settings.html` y `product_form.html` tenían un `<form>` principal que contenía otros `<form>` para eliminar imágenes. HTML no permite formularios anidados y el navegador puede enviar el formulario equivocado.
- **Archivos:**
  - `templates/restaurant/panel/settings.html`
  - `templates/restaurant/panel/product_form.html`
- **Solución:** los botones de eliminación ahora usan `formaction`/`formmethod` sobre el formulario principal y ya no existe ningún formulario anidado.

### Error 2 — El panel permitía saltos de estado inválidos

- **Causa:** tanto el panel del comercio como Super Admin aceptaban cualquier valor de `STATUSES`, por lo que era posible hacer transiciones como `Entregado -> Nuevo`.
- **Archivos:**
  - `routes/restaurant_panel.py`
  - `routes/admin.py`
- **Solución:** se agregó una máquina de estados explícita:

```text
Nuevo -> Contactado / Confirmado / Cancelado
Contactado -> Confirmado / Cancelado
Confirmado -> Preparando / Cancelado
Preparando -> Listo / Cancelado
Listo -> En camino / Entregado / Cancelado
En camino -> Entregado / Cancelado
Entregado -> terminal
Cancelado -> terminal
```

### Error 3 — Validación de horarios dependía demasiado del navegador

- **Causa:** el backend aceptaba strings arbitrarios enviados manualmente para los horarios.
- **Archivo:** `routes/restaurant_panel.py`
- **Solución:** se agregó validación server-side de `HH:MM` y validación de pares completos para el segundo turno.

### Error 4 — Archivos de imagen huérfanos ante rollback

- **Causa:** una imagen podía guardarse en disco y después fallar el `commit()` de PostgreSQL, dejando un archivo que no estaba referenciado por ningún registro.
- **Archivo:** `routes/restaurant_panel.py`
- **Solución:** se conserva la ruta de cada archivo recién creado y se elimina durante el rollback si la transacción falla.

### Error 5 — Contraseñas de comercios sólo tenían validación de longitud en HTML

- **Causa:** la creación/edición confiaba en `minlength` del formulario.
- **Archivo:** `routes/admin.py`
- **Solución:** la validación mínima de 8 caracteres ahora existe también en backend.

### Error 6 — Enlace administrativo denominado "panel" llevaba a la tienda pública

- **Causa:** `/admin/locales/<id>/panel` redirigía a `/comida/<slug>`.
- **Archivo:** `routes/admin.py`
- **Solución:** el enlace ahora dirige al login del comercio con `next=/comercio/panel`, sin conceder permisos de comercio al Super Admin.

### Error 7 — Normalización insuficiente de WhatsApp argentino

- **Causa:** el código sólo quitaba caracteres no numéricos. Un número local como `0291...` podía terminar enviado directamente a `wa.me` sin prefijo internacional.
- **Archivo:** `routes/restaurant_checkout.py`
- **Solución:** se normalizan formatos comunes `+54`, `00 54`, `0...` y números locales de 10 dígitos, sin inventar códigos de área.

### Error 8 — Contador global del carrito gastronómico podía sumar buckets stale

- **Causa:** el context processor sumaba todos los comercios presentes en `session["restaurant_cart"]`.
- **Archivo:** `app.py`
- **Solución:** el contador sólo suma el bucket cuando existe exactamente un carrito gastronómico activo.

## 3. Aislamiento multi-comercio revisado

Las consultas del panel utilizan `restaurant_id` derivado de `RestaurantUser.restaurant_id`, no un `restaurant_id` confiado desde la URL o el cliente.

También se revisaron:

- productos
- categorías
- pedidos
- imágenes de productos
- configuración
- edición de categorías
- asignación de categoría a producto
- modificación de productos

El backend comprueba la pertenencia al comercio antes de operar sobre estos recursos.

## 4. Carrito y checkout

La arquitectura actual mantiene un carrito gastronómico separado del carrito de tienda y usa un bucket por restaurante.

El checkout gastronómico:

1. valida token de formulario;
2. reconstruye productos desde PostgreSQL;
3. recalcula precios en backend;
4. crea `Order`;
5. crea `OrderItem` con snapshot;
6. hace `commit()`;
7. limpia el carrito;
8. genera WhatsApp del restaurante.

La idempotencia existente mediante `checkout_token` se conservó.

## 5. Stock

La confirmación del pedido mantiene el bloqueo de filas de PostgreSQL para evitar dos descuentos concurrentes del mismo stock.

No se descuenta stock simplemente por agregar al carrito.

## 6. Horarios

Se conserva la lógica de:

- zona horaria `America/Argentina/Buenos_Aires`;
- dos turnos;
- horarios que cruzan medianoche;
- comprobación del turno nocturno del día anterior.

Se verificó mediante pruebas puras que un turno `19:00-01:00` continúa abierto a las `00:30` del día siguiente.

## 7. Impresión

**Hallazgo importante:** en la base `MundoMix_marketplace_comida_auditado(1).zip` no existe implementación de impresión gastronómica.

No se agregó una nueva funcionalidad de impresión en esta reparación porque la instrucción de esta actualización es estabilizar y no agregar características nuevas.

Por lo tanto, la prueba de impresión queda marcada como **no disponible en esta base**. Si se quiere recuperar esa función posteriormente, debe hacerse como una actualización separada y no presentarse como una prueba superada de esta auditoría.

## 8. Imágenes

La base auditada utiliza referencias a archivos bajo `UPLOAD_FOLDER`, no columnas PostgreSQL `BYTEA`.

No se cambió el mecanismo de almacenamiento durante esta auditoría para evitar una migración de datos fuera de alcance.

## 9. Pruebas ejecutadas

### Pasaron

- ✔ `python -m compileall -q .`
- ✔ Parseo de todos los templates Jinja2: 0 errores.
- ✔ Revisión de formularios HTML: 0 formularios anidados.
- ✔ Revisión de `url_for`: no se detectaron endpoints gastronómicos faltantes.
- ✔ Prueba de normalización de WhatsApp.
- ✔ Prueba de horarios nocturnos.
- ✔ Prueba de dos turnos horarios.
- ✔ Validación estática de la máquina de estados.
- ✔ Revisión de aislamiento por `restaurant_id` en las rutas del panel.
- ✔ Revisión de que no existe `db.drop_all()` en la aplicación.
- ✔ Integridad estructural del proyecto después de las modificaciones.

### No ejecutables en este entorno

- ❌ PostgreSQL de producción: no hay credenciales/conectividad disponibles.
- ❌ Render HTTP real.
- ❌ Gunicorn real contra la instancia de producción.
- ❌ WhatsApp real.
- ❌ Impresora física.
- ❌ Prueba real de dos tenants sobre una base PostgreSQL.

El entorno de trabajo no tiene Flask/Flask-SQLAlchemy/Werkzeug instalados, por lo que no se simuló un runtime Flask falso ni se presentó una prueba de integración como si fuera real.

## 10. Migraciones

La base contiene actualmente:

```text
migrations/versions/20260915_01_restaurants.py
```

No se creó ninguna migración nueva porque las reparaciones realizadas son de lógica, validación, HTML y flujo, sin cambios de esquema.

No se modificaron tablas ni se borraron registros.

## 11. Archivos modificados

```text
app.py
routes/admin.py
routes/restaurant_checkout.py
routes/restaurant_panel.py
templates/restaurant/panel/product_form.html
templates/restaurant/panel/settings.html
```

Se agregó este informe:

```text
AUDITORIA_GASTRONOMIA.md
```

## 12. Riesgos pendientes fuera de esta reparación

1. No existe protección CSRF explícita en la arquitectura actual.
2. No existe impresión gastronómica en esta versión base.
3. Las imágenes continúan almacenadas como archivos, no `BYTEA`.
4. No se pudo validar el esquema real de la instancia PostgreSQL de Render.
5. Antes de ejecutar `flask db upgrade` en producción debe comprobarse el `alembic_version` real para evitar una cadena de migraciones divergente.

Estos puntos no fueron ocultados ni tratados como pruebas exitosas.
