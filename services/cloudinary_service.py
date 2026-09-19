"""Centralized Cloudinary image handling for MundoMix.

Cloudinary is the permanent image store. PostgreSQL keeps the secure URL and
public_id needed to render and manage each asset.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from flask import current_app
from PIL import Image, UnidentifiedImageError

import cloudinary
import cloudinary.uploader
import cloudinary.utils

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def configure_cloudinary() -> None:
    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = current_app.config.get("CLOUDINARY_API_KEY", "").strip()
    api_secret = current_app.config.get("CLOUDINARY_API_SECRET", "").strip()
    if not all((cloud_name, api_key, api_secret)):
        if current_app.config.get("ENVIRONMENT") == "production":
            raise RuntimeError(
                "Cloudinary no está configurado. Definí CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET en producción."
            )
        return
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)


def _ensure_configured() -> None:
    configure_cloudinary()
    if not current_app.config.get("CLOUDINARY_CLOUD_NAME"):
        raise RuntimeError("Cloudinary no está configurado para esta aplicación.")


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower().lstrip(".")


def validate_image(file_storage) -> dict:
    """Validate extension, declared MIME, size and actual image contents."""
    if not file_storage or not file_storage.filename:
        raise ValueError("No se recibió ninguna imagen.")

    ext = _extension(file_storage.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato de imagen no permitido. Usá JPG, JPEG, PNG o WEBP.")

    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size <= 0:
        raise ValueError("La imagen está vacía.")
    if size > MAX_IMAGE_BYTES:
        raise ValueError("La imagen supera el límite máximo de 8 MB.")

    declared_mime = (file_storage.mimetype or "").lower().split(";", 1)[0].strip()
    if declared_mime and declared_mime not in ALLOWED_MIME:
        raise ValueError("El tipo MIME de la imagen no está permitido.")

    try:
        image = Image.open(stream)
        image.verify()
        actual_format = (image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("El archivo no contiene una imagen válida o está corrupto.") from exc
    finally:
        stream.seek(0)

    if actual_format not in {"JPEG", "PNG", "WEBP"}:
        raise ValueError("El contenido real de la imagen no es JPG, PNG o WEBP.")

    expected = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[ext]
    if actual_format != expected:
        raise ValueError("La extensión no coincide con el formato real de la imagen.")

    return {"extension": ext, "mime": declared_mime or f"image/{'jpeg' if actual_format == 'JPEG' else actual_format.lower()}", "size": size, "format": actual_format}


def upload_image(file_storage, folder: str) -> dict:
    _ensure_configured()
    validate_image(file_storage)
    result = cloudinary.uploader.upload(
        file_storage.stream,
        folder=f"mundomix/{folder.strip('/')}",
        resource_type="image",
        use_filename=False,
        unique_filename=True,
        overwrite=False,
        transformation=[{"quality": "auto", "fetch_format": "auto"}],
        invalidate=True,
    )
    public_id = result.get("public_id")
    secure_url = result.get("secure_url")
    if not public_id or not secure_url:
        raise RuntimeError("Cloudinary no devolvió public_id y secure_url válidos.")
    return {"secure_url": secure_url, "public_id": public_id, "resource_type": result.get("resource_type", "image")}


def delete_image(public_id: str | None) -> bool:
    if not public_id:
        return True
    _ensure_configured()
    result = cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    status = result.get("result")
    if status not in {"ok", "not found"}:
        raise RuntimeError(f"Cloudinary no pudo eliminar el recurso {public_id!r}: {result}")
    return True


def replace_image(file_storage, old_public_id: str | None, folder: str) -> dict:
    """Upload the replacement first; delete the old asset only after DB commit."""
    # old_public_id is intentionally not deleted here because the database
    # transaction belongs to the route. This prevents losing the old image
    # when the new upload or DB commit fails.
    return upload_image(file_storage, folder)


def build_image_url(public_id: str | None, secure_url: str | None = None, width: int | None = None, height: int | None = None) -> str:
    if not public_id:
        return secure_url or ""
    _ensure_configured()
    transformation = [{"quality": "auto", "fetch_format": "auto"}]
    if width or height:
        transformation.append({"width": width, "height": height, "crop": "limit"})
    return cloudinary.CloudinaryImage(public_id).build_url(secure=True, transformation=transformation)


def extract_public_id_from_cloudinary_url(url: str | None) -> str | None:
    """Best-effort extraction for assets already uploaded to Cloudinary."""
    if not url or "res.cloudinary.com/" not in url or "/upload/" not in url:
        return None
    path = url.split("/upload/", 1)[1].split("?", 1)[0]
    parts = path.split("/")
    while parts and (parts[0].startswith("v") and parts[0][1:].isdigit()):
        parts.pop(0)
    # Remove common transformation segments when present.
    while parts and ("=" in parts[0] or parts[0].split(",")[0] in {"f_auto", "q_auto", "c_fill", "c_limit"}):
        parts.pop(0)
    if not parts:
        return None
    filename = parts[-1]
    stem = filename.rsplit(".", 1)[0]
    parts[-1] = stem
    return "/".join(parts)
