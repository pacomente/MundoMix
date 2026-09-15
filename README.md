# MundoMix — E-commerce + PostgreSQL + Gunicorn

MundoMix es una tienda online desarrollada con **Python + Flask + SQLAlchemy + Jinja2 + HTML5 + CSS3 + JavaScript**.

La aplicación mantiene su arquitectura existente y queda preparada para:

- **Desarrollo local:** Flask + SQLite (compatibilidad con la instalación local existente).
- **Producción:** **Gunicorn → Flask → SQLAlchemy → PostgreSQL**.
- **Migración:** script seguro **SQLite → PostgreSQL**, conservando IDs y relaciones.

> La SQLite existente no se elimina ni se sobrescribe durante la migración.

## Funcionalidades conservadas

- Homepage responsive con banners.
- Catálogo con búsqueda, filtros, ordenamiento y paginación.
- Productos y categorías.
- Carrito.
- Dos precios finales por producto:
  - `price_delivery`: precio final con envío incluido.
  - `price_pickup`: precio final retirando en local.
- Checkout con pedido guardado antes de WhatsApp.
- Estados de pedido y descuento de stock al confirmar.
- Panel administrativo responsive.
- Productos, categorías, banners, pedidos y configuración.
- Uploads JPG/JPEG/PNG/WEBP.
- Hash de contraseñas con Werkzeug.
- `/health` con comprobación de base de datos.
- Endpoint de Chrome DevTools.

---

# 1. Requisitos

- Python 3.12+.
- PostgreSQL para producción.
- Gunicorn para producción Linux/Unix.
- Windows continúa siendo válido para desarrollo.

Gunicorn está diseñado principalmente para Linux/Unix. Para el servidor real se recomienda Linux. En Windows podés seguir ejecutando Flask para desarrollo y usar PostgreSQL local si querés probar la base antes del despliegue.

---

# 2. Instalación en Windows

Crear entorno virtual:

```cmd
python -m venv .venv
```

Activarlo:

```cmd
.venv\Scripts\activate
```

Instalar dependencias:

```cmd
pip install -r requirements.txt
```

Copiar `.env.example` a `.env` y completar los valores.

Para una instalación local nueva con SQLite, `python init_db.py` crea las tablas y el primer administrador. Antes de ejecutarlo, definir una contraseña inicial mediante `ADMIN_INITIAL_PASSWORD`.

Ejemplo en CMD:

```cmd
set ADMIN_INITIAL_PASSWORD=una-clave-segura
python init_db.py
```

Luego:

```cmd
python app.py
```

Abrir:

```text
http://127.0.0.1:5000
```

---

# 3. Variables de entorno

El archivo `.env` real nunca debe subirse a Git.

Ejemplo para producción:

```env
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=una-clave-larga-y-aleatoria
DATABASE_URL=postgresql+psycopg://usuario:password@localhost:5432/mundomix
WHATSAPP_NUMBER=
UPLOAD_FOLDER=uploads
SESSION_COOKIE_SECURE=1
PORT=8000
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=30
```

`DATABASE_URL` es obligatoria en producción y debe apuntar a PostgreSQL. No se aceptará SQLite como base principal cuando `FLASK_ENV=production`.

Para generar `SECRET_KEY`:

```cmd
python -c "import secrets; print(secrets.token_hex(32))"
```

`SESSION_COOKIE_SECURE=1` corresponde a producción detrás de HTTPS. Para una prueba local directa por HTTP puede utilizarse temporalmente `0`.

---

# 4. PostgreSQL

Crear una base y un usuario en PostgreSQL según la política de seguridad del servidor.

Ejemplo conceptual:

```text
Base: mundomix
Usuario: mundomix_app
```

No colocar la contraseña real en este README, en el código ni en `.env.example`.

La aplicación utiliza exclusivamente `DATABASE_URL` para decidir dónde está PostgreSQL. No hay `localhost` ni `127.0.0.1` hardcodeados en la conexión.

El driver utilizado es:

```text
psycopg
```

---

# 5. Migrar SQLite → PostgreSQL

La migración se realiza con:

```bash
python scripts/migrate_sqlite_to_postgres.py
```

Por defecto toma:

```text
instance/mundomix.db
```

También se puede indicar otra SQLite:

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite instance/mundomix.db
```

### Seguridad de la migración

Antes de leer la SQLite, el script crea automáticamente un backup en:

```text
backup/mundomix_YYYYMMDD_HHMMSS.db
```

La SQLite original no se modifica ni se elimina.

El script además se niega por defecto a insertar en un PostgreSQL que ya contiene registros. Esto evita duplicaciones accidentales. Solo utilizar `--allow-existing-target` después de revisar expresamente el destino:

```bash
python scripts/migrate_sqlite_to_postgres.py --allow-existing-target
```

### Qué conserva

- IDs.
- Relaciones.
- Productos.
- Categorías.
- Pedidos.
- Detalles de pedidos.
- Administradores.
- Banners.
- Configuración.
- Stock.
- Precios.
- Estados.
- Fechas.

Al finalizar compara automáticamente la cantidad de registros de cada tabla entre SQLite y PostgreSQL y sincroniza las secuencias de IDs de PostgreSQL.

Si encuentra una incompatibilidad de esquema o una diferencia de cantidades, la operación falla y muestra el problema en lugar de declarar una migración exitosa.

---

# 6. Orden de tablas migradas

El orden respeta las relaciones actuales:

```text
category
admin
banner
setting
product
order
order_item
```

Las tablas dependientes se insertan después de sus tablas padre.

---

# 7. Estructura actual de datos

Los modelos actuales son:

```text
Category
Product
Order
OrderItem
Admin
Banner
Setting
```

Relaciones principales:

```text
Category 1 ─── N Product
Order    1 ─── N OrderItem
```

`OrderItem.product_id` puede ser `NULL` porque el sistema conserva el nombre del producto en `product_name_snapshot` para mantener el histórico del pedido.

---

# 8. Migraciones futuras

El proyecto incorpora **Flask-Migrate/Alembic** para cambios futuros de esquema.

Una vez instalado el proyecto, si todavía no existe el directorio `migrations`, inicializarlo una sola vez:

```bash
flask --app wsgi db init
```

Crear una migración después de modificar modelos:

```bash
flask --app wsgi db migrate -m "describe el cambio"
```

Revisar la migración generada antes de ejecutarla.

Aplicarla:

```bash
flask --app wsgi db upgrade
```

**No ejecutar migraciones destructivas sin revisar primero el archivo generado.**

En producción, los cambios de esquema deben realizarse mediante Alembic/Flask-Migrate y no mediante `db.drop_all()`.

---

# 9. Importante sobre `db.create_all()`

En desarrollo, MundoMix puede crear tablas faltantes automáticamente para facilitar una instalación local nueva.

En producción esto no se ejecuta automáticamente. El esquema debe estar preparado mediante la migración inicial o mediante Flask-Migrate/Alembic.

Esto evita que un despliegue de producción oculte un problema de migración de esquema.

Nunca se utiliza:

```python
db.drop_all()
```

---

# 10. Gunicorn

El punto de entrada WSGI es:

```text
wsgi.py
```

Expone:

```python
app = create_app()
```

El comando de producción es:

```bash
gunicorn wsgi:app
```

La configuración está en:

```text
gunicorn.conf.py
```

Valores iniciales:

```text
bind = 0.0.0.0:8000
workers = 2
threads = 4
timeout = 120
```

El puerto puede cambiarse con:

```env
PORT=8000
```

Los workers, threads y timeout también pueden configurarse mediante variables de entorno.

A diferencia de la versión anterior, la configuración ya no está orientada a SQLite en producción: PostgreSQL permite una concurrencia mayor y SQLAlchemy utiliza un pool conservador con `pool_pre_ping`, `pool_recycle`, `pool_size`, `max_overflow` y `pool_timeout`.

---

# 11. Desarrollo vs producción

### Desarrollo

```bash
python app.py
```

### Producción

```bash
gunicorn wsgi:app
```

`app.run()` queda únicamente como servidor de desarrollo local.

---

# 12. Linux / servidor

Crear entorno:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalar:

```bash
pip install -r requirements.txt
```

Configurar `.env` con PostgreSQL.

Migrar la SQLite, si existe y corresponde:

```bash
python scripts/migrate_sqlite_to_postgres.py
```

Si el esquema ya está gestionado por Flask-Migrate, aplicar las migraciones pendientes:

```bash
flask --app wsgi db upgrade
```

Iniciar:

```bash
gunicorn wsgi:app
```

Arquitectura recomendada:

```text
Internet
   ↓
Nginx / Reverse Proxy
   ↓
Gunicorn
   ↓
Flask
   ↓
SQLAlchemy
   ↓
PostgreSQL
```

Nginx no forma parte de este repositorio.

---

# 13. Health check

Endpoint:

```text
/health
```

Cuando Flask y PostgreSQL están disponibles responde:

```json
{"status":"ok"}
```

HTTP `200`.

El endpoint ejecuta internamente `SELECT 1`. Si PostgreSQL no está disponible, responde `503` y el detalle queda registrado en logs sin exponer credenciales.

---

# 14. Chrome DevTools

Chrome puede solicitar:

```text
/.well-known/appspecific/com.chrome.devtools.json
```

MundoMix responde `200 OK` con JSON válido y no trata esa solicitud automática como un error 404.

---

# 15. Panel administrativo

Acceso:

```text
/admin/login
```

Rutas principales:

```text
/admin
/admin/products
/admin/categories
/admin/orders
/admin/banners
/admin/settings
```

El dashboard consulta directamente la base configurada por `DATABASE_URL`.

No se utilizan estadísticas simuladas.

---

# 16. Administrador inicial

En una instalación nueva, `init_db.py` crea el usuario:

```text
admin
```

La contraseña inicial **no está hardcodeada**. Debe proporcionarse mediante:

```env
ADMIN_INITIAL_PASSWORD=una-clave-segura
```

Después de crear el administrador, eliminar o cambiar esa variable y utilizar una contraseña segura.

Las contraseñas se guardan mediante hash de Werkzeug.

---

# 17. Precios y pedidos

Se mantiene la lógica existente:

```text
price_delivery = precio final con envío incluido
price_pickup   = precio final retirando en local
```

No se agrega un costo de envío adicional.

El checkout guarda el pedido antes de mostrar/redirigir a WhatsApp.

---

# 18. Stock

El stock continúa descontándose al confirmar el pedido según la lógica existente.

No se descuenta simplemente por iniciar el checkout o generar un pedido de WhatsApp.

---

# 19. Uploads

Las imágenes siguen fuera de PostgreSQL:

```text
uploads/products/
uploads/banners/
uploads/categories/
```

PostgreSQL conserva las rutas/nombres almacenados en los modelos.

Los archivos existentes no forman parte de la migración SQL y no deben eliminarse durante ella.

---

# 20. Seguridad

- `SECRET_KEY` obligatoria en producción.
- No se utilizan credenciales PostgreSQL hardcodeadas.
- `.env` está ignorado por Git.
- Passwords con hash de Werkzeug.
- Uploads limitados a JPG/JPEG/PNG/WEBP.
- Nombres de uploads generados con UUID y `secure_filename()`.
- Cookies HTTPOnly y SameSite.
- Errores 403/404/405/500 sin traceback al usuario.
- Excepciones registradas en logs.
- Pool PostgreSQL con `pool_pre_ping`.
- No se utiliza `drop_all()`.

---

# 21. Verificación manual después del despliegue

Comprobar como mínimo:

```text
/
/health
/admin/login
/admin
/admin/products
/admin/categories
/admin/orders
/admin/banners
/admin/settings
/.well-known/appspecific/com.chrome.devtools.json
```

También comprobar:

- CSS.
- JavaScript.
- imágenes.
- login/logout.
- creación/modificación de productos.
- creación de pedidos.
- aparición del pedido en administración.
- stock.
- banners.
- configuración.
- WhatsApp.

---

# 22. Nota sobre pruebas de entorno

El repositorio incluye validaciones estáticas y un script de migración verificable, pero una prueba real de PostgreSQL requiere una instancia PostgreSQL accesible y credenciales válidas. No deben inventarse resultados de esa prueba.

Antes de declarar una migración productiva, ejecutar el script y conservar el informe de cantidades que imprime al finalizar.

## Marketplace de locales gastronómicos

MundoMix incorpora un módulo multi-comercio para locales de comida rápida sin reemplazar la tienda de productos propia.

### Flujo público

- `/comida`: catálogo de locales activos.
- `/comida/<slug>`: mini tienda pública del local.
- `/comida/<slug>/carrito`: carrito aislado del local.
- `/comida/<slug>/checkout`: checkout del local y generación del pedido.
- El pedido se guarda en `Order` antes de redirigir a `https://wa.me/` con el WhatsApp almacenado en `Restaurant.whatsapp`.

### Acceso de comercios

- `/comercio/login`
- `/comercio/panel`

Cada usuario está asociado a un único `Restaurant`. Todas las consultas del panel filtran por `restaurant_id`; un comercio no puede acceder por URL a recursos de otro.

### Administración MundoMix

En `/admin` existe **Locales gastronómicos** para crear, activar/desactivar y editar locales y sus credenciales iniciales. El alta crea también los siete registros de horarios.

### Base de datos

Se reutilizan `Order` y `OrderItem` para no duplicar el sistema histórico de pedidos. Los pedidos propios mantienen `product_id`; los gastronómicos utilizan `restaurant_id` y `restaurant_product_id`, además del snapshot de nombre/precio ya existente.

Nuevas tablas:

- `restaurant`
- `restaurant_user`
- `restaurant_category`
- `restaurant_product`
- `restaurant_hour`

La migración incremental está en `migrations/versions/20260915_01_restaurants.py`. No ejecuta `drop_all` y el downgrade es intencionalmente no destructivo.

### Migración en producción

Después de desplegar el código y confirmar que `DATABASE_URL` apunta a PostgreSQL:

```bash
flask --app wsgi:app db upgrade
```

Luego comprobar:

```bash
curl https://TU-DOMINIO/health
```

Debe devolver `{"status":"ok"}`.

### Imágenes

El proyecto existente actualmente almacena imágenes mediante referencias a archivos bajo `UPLOAD_FOLDER`; este módulo reutiliza ese mecanismo y Pillow para validar imágenes. No se inventó una migración BYTEA sobre el esquema existente porque el modelo real inspeccionado no contiene columnas binarias `BYTEA`. Si se decide migrar también las imágenes históricas a PostgreSQL, debe hacerse como una migración separada y con backup/validación de los archivos existentes.
