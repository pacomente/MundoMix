# MundoMix — E-commerce local

MundoMix es una tienda online local desarrollada con **Python + Flask + SQLite + SQLAlchemy + Jinja2 + HTML5 + CSS3 + JavaScript**.

La aplicación conserva su arquitectura existente y está preparada para ejecutarse:

- **Desarrollo:** servidor integrado de Flask.
- **Producción:** **Gunicorn → Flask → SQLAlchemy → SQLite**.

## Funcionalidades

- Homepage responsive con banners administrables.
- Catálogo con búsqueda, filtros, ordenamiento y paginación.
- Página de producto con galería y relacionados.
- Carrito dinámico.
- Dos precios finales por producto:
  - `price_delivery`: precio final con envío incluido.
  - `price_pickup`: precio final retirando en local.
- Checkout por WhatsApp con pedido guardado antes de abrir WhatsApp.
- Estados de pedido y descuento de stock al confirmar.
- Panel administrativo responsive.
- Productos, categorías, banners, pedidos y configuración.
- Upload de imágenes JPG/JPEG/PNG/WEBP.
- Contraseñas almacenadas mediante hash de Werkzeug.
- Endpoint público `/health` para health checks.
- Endpoint público de Chrome DevTools en `/.well-known/appspecific/com.chrome.devtools.json`.

## Requisitos

- Python 3.12 o superior recomendado.
- En producción Linux/Unix, Gunicorn.
- SQLite se mantiene como base de datos actual.

> Gunicorn está diseñado principalmente para Linux/Unix. En Windows puede instalarse en algunos entornos, pero no es el escenario de despliegue recomendado. Para producción real se recomienda Linux.

## Instalación en Windows

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

Copiar `.env.example` como `.env` y ajustar sus valores.

Inicializar la base si es una instalación nueva:

```cmd
python init_db.py
```

Iniciar en desarrollo:

```cmd
python app.py
```

Abrir:

```text
http://127.0.0.1:5000
```

## Variables de entorno

`.env` no debe subirse al repositorio.

Variables principales:

```env
SECRET_KEY=una-clave-larga-y-aleatoria
FLASK_ENV=production
FLASK_DEBUG=0
DATABASE_URL=sqlite:///instance/mundomix.db
WHATSAPP_NUMBER=
UPLOAD_FOLDER=uploads
SESSION_COOKIE_SECURE=1
PORT=8000
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120
```

En producción, `SECRET_KEY` es obligatoria. Si falta, MundoMix detiene el arranque con un error claro en lugar de utilizar una clave insegura.

Para generar una clave segura:

```cmd
python -c "import secrets; print(secrets.token_hex(32))"
```

`SESSION_COOKIE_SECURE=1` debe mantenerse cuando el sitio está detrás de HTTPS. Para una prueba directa local por HTTP en modo producción se puede utilizar temporalmente `SESSION_COOKIE_SECURE=0`.

## Base de datos

La aplicación utiliza SQLite + SQLAlchemy.

Por defecto busca:

```text
instance/mundomix.db
```

La ruta se construye desde el directorio real del proyecto, por lo que no depende del directorio desde el cual se lance Gunicorn.

El arranque ejecuta `db.create_all()` únicamente para crear tablas que todavía no existan. **No utiliza `drop_all()` y no elimina productos, pedidos ni otros datos existentes.**

Si ya existe una base de datos, debe conservarse. `db.create_all()` no es un sistema de migraciones: si en el futuro se agregan o modifican columnas, debe utilizarse una migración segura antes de desplegar ese cambio.

## Administrador

Acceso:

```text
/admin/login
```

Usuario inicial de una instalación nueva:

```text
admin
```

Contraseña inicial:

```text
cambiar-esta-clave
```

**Cambiar la contraseña inicial antes de utilizar el sistema en producción.** Las contraseñas se almacenan mediante hash de Werkzeug.

Rutas administrativas principales:

```text
/admin
/admin/products
/admin/categories
/admin/orders
/admin/banners
/admin/settings
```

## Producción con Gunicorn

El punto de entrada WSGI es:

```text
wsgi.py
```

Expone:

```python
app = create_app()
```

Por lo tanto, el comando de producción es:

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

El puerto se puede cambiar con:

```env
PORT=8000
```

También se pueden ajustar workers, threads y timeout mediante variables `GUNICORN_WORKERS`, `GUNICORN_THREADS` y `GUNICORN_TIMEOUT`.

La configuración es conservadora porque MundoMix utiliza SQLite, que tiene limitaciones de escritura concurrente. No conviene aumentar indiscriminadamente el número de workers.

## Linux / servidor de producción

Crear entorno:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalar:

```bash
pip install -r requirements.txt
```

Configurar `.env` y ejecutar:

```bash
gunicorn wsgi:app
```

Gunicorn escuchará por defecto en:

```text
0.0.0.0:8000
```

La arquitectura recomendada para Internet es:

```text
Internet
   ↓
Nginx / reverse proxy
   ↓
Gunicorn
   ↓
Flask
   ↓
SQLAlchemy
   ↓
SQLite
```

Nginx no forma parte de este proyecto y debe configurarse en el servidor Linux si se necesita HTTPS, dominio, archivos estáticos servidos directamente y reverse proxy.

## Health check

Endpoint público:

```text
/health
```

Respuesta:

```json
{"status":"ok"}
```

HTTP `200`.

No requiere autenticación y no expone información sensible.

## Chrome DevTools

Chrome puede solicitar automáticamente:

```text
/.well-known/appspecific/com.chrome.devtools.json
```

MundoMix responde `200 OK` con JSON vacío para que esta solicitud automática no sea tratada como un 404.

## Archivos estáticos y uploads

Los archivos estáticos se encuentran en:

```text
static/
```

Las imágenes subidas se almacenan en:

```text
uploads/products/
uploads/banners/
```

Los nombres generados para uploads utilizan UUID y se restringen a JPG/JPEG/PNG/WEBP.

En un servidor Linux hay que garantizar permisos de escritura para el proceso que ejecuta Gunicorn sobre `uploads/` e `instance/`.

## Precios

Esta lógica comercial se mantiene en todo el proyecto:

```text
price_delivery = precio final con envío incluido
price_pickup   = precio final retirando en local
```

No se agrega una tarifa de envío adicional.

## Stock

Agregar productos al carrito no descuenta stock.

El pedido se guarda como solicitud y el stock se descuenta al pasar el pedido a `Confirmado`, según la lógica existente.

## Estructura

```text
app.py
wsgi.py
gunicorn.conf.py
config.py
extensions.py
init_db.py
requirements.txt
.env.example
models/
routes/
templates/
static/
uploads/
instance/
```

## Pruebas locales recomendadas

Desarrollo:

```cmd
python app.py
```

Comprobar:

```text
/
/catalogo
/carrito/
/health
/admin/login
/.well-known/appspecific/com.chrome.devtools.json
```

Producción en Linux:

```bash
gunicorn wsgi:app
```

Comprobar:

```text
/health
/admin/login
/admin
/admin/products
/admin/categories
/admin/orders
/admin/banners
/admin/settings
```

## Importante sobre las pruebas de este paquete

El código fuente, sintaxis Python y templates pueden validarse sin levantar la aplicación. La prueba HTTP real requiere instalar las dependencias de `requirements.txt` y ejecutar Flask/Gunicorn en un entorno que disponga de esas dependencias.

El entorno donde se preparó este paquete no tenía Flask ni Gunicorn instalados y no tenía acceso de red para descargarlos, por lo que **no se declara como realizada una prueba HTTP real de Gunicorn desde ese entorno**.
