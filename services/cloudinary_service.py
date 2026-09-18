"""Centralized, data-safe Cloudinary image storage for MundoMix."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

from flask import current_app
from PIL import Image, UnidentifiedImageError

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class CloudinaryAsset:
    url: str
    public_id: str


def _client():
    """Configure and return Cloudinary lazily so local imports/tests do not need it."""
    import cloudinary

    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = current_app.config.get("CLOUDINARY_API_KEY", "").strip()
    api_secret = current_app.config.get("CLOUDINARY_API_SECRET", "").strip()
    if not all((cloud_name, api_key, api_secret)):
        raise RuntimeError(
            "Cloudinary no está configurado. Definí CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET."
        )
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
    return cloudinary


def validate_image(file_storage) -> bytes:
    if not file_storage or not file_storage.filename:
        raise ValueError("No se recibió ninguna imagen.")

    filename = file_storage.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato de imagen no permitido. Usá JPG, JPEG, PNG o WEBP.")

    mime = (file_storage.mimetype or "").lower().split(";", 1)[0].strip()
    if mime and mime not in ALLOWED_MIMES:
        raise ValueError("El tipo MIME de la imagen no está permitido.")

    raw = file_storage.read(MAX_IMAGE_BYTES + 1)
    file_storage.stream.seek(0)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen no puede superar 8 MB.")
    if not raw:
        raise ValueError("La imagen está vacía.")

    try:
        with Image.open(BytesIO(raw)) as image:
            detected = (image.format or "").upper()
            if detected not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("El contenido real del archivo no es una imagen JPG, PNG o WEBP válida.")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("El archivo no contiene una imagen válida.") from exc
    return raw


def upload_image(file_storage, folder: str) -> CloudinaryAsset:
    raw = validate_image(file_storage)
    cloudinary = _client()
    from cloudinary.uploader import upload

    result = upload(
        BytesIO(raw),
        resource_type="image",
        folder=f"mundomix/{folder.strip('/')}",
        public_id=uuid4().hex,
        overwrite=False,
        use_filename=False,
        unique_filename=True,
        transformation=[{"quality": "auto", "fetch_format": "auto"}],
    )
    url = result.get("secure_url")
    public_id = result.get("public_id")
    if not url or not public_id:
        raise RuntimeError("Cloudinary no devolvió una URL o public_id válidos.")
    return CloudinaryAsset(url=url, public_id=public_id)


def delete_image(public_id: str | None) -> bool:
    if not public_id:
        return False
    cloudinary = _client()
    from cloudinary.uploader import destroy

    result = destroy(public_id, resource_type="image", invalidate=True)
    status = result.get("result")
    if status not in {"ok", "not found"}:
        raise RuntimeError(f"Cloudinary no pudo eliminar {public_id!r}: {result}")
    return status == "ok"


def is_external_image(value: str | None) -> bool:
    value = (value or "").strip().lower()
    return value.startswith("https://") or value.startswith("http://")
