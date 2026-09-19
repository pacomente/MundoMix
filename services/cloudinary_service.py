"""Centralized Cloudinary image operations for MundoMix."""
from __future__ import annotations

import io
import mimetypes
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from cloudinary.utils import cloudinary_url
from flask import current_app
from PIL import Image, UnidentifiedImageError

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}


def configure_cloudinary() -> None:
    """Configure the SDK from environment-backed Flask settings."""
    cloudinary.config(
        cloud_name=current_app.config.get("CLOUDINARY_CLOUD_NAME"),
        api_key=current_app.config.get("CLOUDINARY_API_KEY"),
        api_secret=current_app.config.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def is_configured() -> bool:
    return all(
        current_app.config.get(key)
        for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    )


def ensure_configured() -> None:
    if not is_configured():
        raise RuntimeError(
            "Cloudinary no está configurado. Definí CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET en el entorno."
        )
    configure_cloudinary()


def validate_image(file: BinaryIO, *, max_bytes: int | None = None) -> dict:
    """Validate extension, size, MIME metadata and actual image content."""
    if not file or not getattr(file, "filename", None):
        raise ValueError("No se recibió una imagen.")

    filename = Path(str(file.filename)).name
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato de imagen no permitido. Usá JPG, JPEG, PNG o WEBP.")

    try:
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
    except (AttributeError, OSError) as exc:
        raise ValueError("No se pudo leer el archivo de imagen.") from exc

    if not size:
        raise ValueError("La imagen está vacía.")
    if max_bytes is not None and size > max_bytes:
        raise ValueError("La imagen supera el límite máximo permitido.")

    content_type = (getattr(file, "mimetype", None) or mimetypes.guess_type(filename)[0] or "").lower()
    if content_type and content_type not in ALLOWED_MIMES:
        raise ValueError("El tipo MIME de la imagen no está permitido.")

    try:
        with Image.open(file) as image:
            image.verify()
        file.seek(0)
        with Image.open(file) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            image.load()
    except (UnidentifiedImageError, OSError) as exc:
        file.seek(0)
        raise ValueError("El archivo no contiene una imagen válida.") from exc
    finally:
        try:
            file.seek(0)
        except OSError:
            pass

    if image_format not in ALLOWED_FORMATS:
        raise ValueError("El contenido real de la imagen no coincide con un formato permitido.")

    return {
        "filename": filename,
        "extension": "jpg" if image_format == "JPEG" else image_format.lower(),
        "content_type": content_type,
        "size": size,
        "format": image_format,
        "width": width,
        "height": height,
    }


def upload_image(file: BinaryIO, folder: str, *, public_id: str | None = None) -> dict:
    """Validate and upload an image, returning secure_url and public_id."""
    ensure_configured()
    validate_image(file, max_bytes=current_app.config.get("MAX_CONTENT_LENGTH"))
    safe_public_id = public_id or uuid4().hex
    try:
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            public_id=safe_public_id,
            resource_type="image",
            overwrite=False,
            use_filename=False,
            unique_filename=False,
            invalidate=True,
        )
    except CloudinaryError as exc:
        current_app.logger.exception("Cloudinary upload error")
        raise RuntimeError("No se pudo subir la imagen a Cloudinary.") from exc

    secure_url = result.get("secure_url")
    returned_public_id = result.get("public_id")
    if not secure_url or not returned_public_id:
        raise RuntimeError("Cloudinary no devolvió una URL segura o public_id válido.")
    return {"secure_url": secure_url, "public_id": returned_public_id, "raw": result}


def delete_image(public_id: str | None) -> bool:
    """Delete a Cloudinary image by public_id. Missing IDs are a no-op."""
    if not public_id:
        return True
    ensure_configured()
    try:
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )
    except CloudinaryError as exc:
        current_app.logger.exception("Cloudinary delete error for %s", public_id)
        raise RuntimeError("No se pudo eliminar la imagen de Cloudinary.") from exc

    status = result.get("result")
    if status not in {"ok", "not found"}:
        raise RuntimeError(f"Cloudinary no pudo eliminar el recurso: {status or 'respuesta desconocida'}")
    return True


def replace_image(file: BinaryIO, folder: str, old_public_id: str | None = None, *, public_id: str | None = None) -> dict:
    """Upload the replacement first. Caller deletes the old resource after DB commit."""
    uploaded = upload_image(file, folder, public_id=public_id)
    uploaded["old_public_id"] = old_public_id
    return uploaded


def build_image_url(public_id: str | None, *, width: int | None = None, height: int | None = None) -> str | None:
    """Build an optimized delivery URL from a Cloudinary public_id."""
    if not public_id:
        return None
    ensure_configured()
    options = [{"quality": "auto", "fetch_format": "auto"}]
    if width or height:
        options.append({"width": width, "height": height, "crop": "limit"})
    url, _ = cloudinary_url(public_id, secure=True, transformation=options)
    return url


def public_id_from_url(url: str | None) -> str | None:
    """Best-effort helper for migration diagnostics; DB public_ids remain authoritative."""
    if not url or "res.cloudinary.com/" not in url:
        return None
    return None
