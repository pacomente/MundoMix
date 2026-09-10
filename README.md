# MundoMix — E-commerce local

Actualización integral de una tienda online local con **Python + Flask + SQLite + SQLAlchemy + HTML5 + CSS3 + JavaScript**.

## Qué incluye

- Homepage responsive con banners administrables.
- Catálogo con búsqueda por nombre, SKU, descripción y categoría.
- Filtros por categoría, precio, disponibilidad y destacados.
- Ordenamiento por relevancia, precio, recientes y nombre.
- Paginación.
- Página de producto con galería y relacionados.
- Carrito dinámico.
- Dos precios finales por producto:
  - `price_delivery`: precio final **con envío incluido**.
  - `price_pickup`: precio final **retirando en local**.
- Checkout por WhatsApp.
- Pedido persistido antes de abrir WhatsApp.
- Estados de pedido y descuento de stock al confirmar.
- Panel administrativo responsive.
- Productos, categorías, banners, pedidos y configuración.
- Upload seguro de imágenes JPG/JPEG/PNG/WEBP.
- Contraseñas con hash de Werkzeug.
- Feedback visual, estados vacíos y diseño mobile-first.

## Instalación

### Windows

```bash
python -m venv venv
venv\\Scripts\\activate
```

### Linux/macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

Instalá dependencias:

```bash
pip install -r requirements.txt
```

Copiá `.env.example` como `.env` y configurá una `SECRET_KEY` segura.

Inicializá la base:

```bash
python init_db.py
```

Iniciá:

```bash
python app.py
```

Abrí `http://127.0.0.1:5000`.

## Administrador

URL: `/admin/login`

Usuario inicial: `admin`

Contraseña inicial: `cambiar-esta-clave`

**Cambiala antes de producción.**

## WhatsApp

Podés configurar el número desde **Administrador → Configuración**. También se acepta `WHATSAPP_NUMBER` en `.env`.

Formato recomendado: código de país + número, sin `+`, espacios ni guiones.

## Precios

Esta regla es obligatoria en todo el proyecto:

`price_delivery` = precio final con envío incluido.

`price_pickup` = precio final retirando en local.

No existe una tarifa de envío adicional. El carrito y checkout usan el precio correspondiente al método seleccionado.

## Stock

Agregar al carrito nunca permite superar el stock. Crear el pedido no descuenta stock porque todavía es una solicitud. Al cambiar un pedido a `Confirmado`, el stock se descuenta una sola vez.

Si después se cambia el estado, el stock **no se repone automáticamente** para evitar ajustes silenciosos. Hacé la corrección de inventario manualmente si corresponde.

## Estructura

- `app.py`: factory y configuración de rutas globales.
- `config.py`: configuración y variables de entorno.
- `models/`: modelos SQLAlchemy.
- `routes/`: storefront, carrito, checkout y administración.
- `templates/`: tienda y panel admin.
- `static/css/`: estilos de tienda y admin.
- `static/js/`: microinteracciones y comportamiento UI.
- `uploads/`: imágenes subidas.
- `instance/`: SQLite.

## Producción

Usá una `SECRET_KEY` aleatoria, HTTPS, servidor WSGI (Waitress/Gunicorn), backups y migraciones antes de cambios de esquema. Para mayor volumen, podés migrar SQLite a PostgreSQL/MySQL mediante `DATABASE_URL`.
