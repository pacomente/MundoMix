"""Centralized Cloudinary image service for MundoMix.

All new image writes go directly to Cloudinary. Legacy filesystem paths are
kept only as migration/fallback references until explicitly retired.
"""
import io
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from PIL import Image

try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.utils
except ImportError:  # Allows static tooling to import the module before install.
    cloudinary = None

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def cloudinary_public_id_from_url(value):
    """Extract a public_id from a standard Cloudinary delivery URL when possible."""
    if not value or "res.cloudinary.com" not in str(value):
        return None
    path = urlparse(str(value)).path.lstrip("/")
    parts = path.split("/")
    try:
        upload_index = parts.index("upload")
    except ValueError:
        return None
    resource = parts[upload_index + 1:]
    if not resource:
        return None
    # Strip transformation components (v123/... or c_.../q_auto/... style).
    while resource and (resource[0].startswith("v") and resource[0][1:].isdigit()):
        resource = resource[1:]
    while resource and ("_" in resource[0] or resource[0].startswith("q") or resource[0].startswith("f")) and "/" in "/".join(resource):
        if resource[0].startswith("v") and resource[0][1:].isdigit():
            resource = resource[1:]
        elif any(resource[0].startswith(prefix) for prefix in ("c_", "q_", "f_", "w_", "h_", "ar_", "g_", "dpr_", "e_", "fl_")):
            resource = resource[1:]
        else:
            break
    if not resource:
        return None
    last = resource[-1]
    if "." in last:
        resource[-1] = last.rsplit(".", 1)[0]
    return "/".join(resource) or None


def configure():
    if cloudinary is None:
        raise RuntimeError("El SDK de Cloudinary no está instalado. Ejecutá pip install -r requirements.txt.")
    name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
    if not all((name, key, secret)):
        raise RuntimeError("Faltan CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY o CLOUDINARY_API_SECRET.")
    cloudinary.config(cloud_name=name, api_key=key, api_secret=secret, secure=True)


def validate_image(file):
    if not file or not getattr(file, "filename", ""):
        return None
    filename = file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato de imagen no permitido. Usá JPG, JPEG, PNG o WEBP.")
    stream = getattr(file, "stream", file)
    stream.seek(0)
    raw = stream.read(MAX_IMAGE_BYTES + 1)
    stream.seek(0)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen no puede superar 8 MB.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        fmt = image.format
    except Exception as exc:
        raise ValueError("El archivo no contiene una imagen válida.") from exc
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("El contenido real de la imagen no es JPG, PNG o WEBP.")
    return raw, fmt.lower()


def upload_image(file, folder, public_id=None):
    validated = validate_image(file)
    if not validated:
        return None
    raw, _ = validated
    configure()
    public_id = public_id or uuid4().hex
    result = cloudinary.uploader.upload(
        io.BytesIO(raw),
        folder=folder,
        public_id=public_id,
        overwrite=False,
        resource_type="image",
        unique_filename=False,
        use_filename=False,
        invalidate=True,
    )
    pid = result.get("public_id")
    optimized_url = generate_url(pid, result.get("secure_url") or result.get("url")) if pid else (result.get("secure_url") or result.get("url"))
    return {
        "secure_url": optimized_url,
        "public_id": pid,
    }


def delete_image(public_id):
    if not public_id:
        return True
    configure()
    result = cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    status = result.get("result")
    if status not in {"ok", "not found"}:
        raise RuntimeError(f"Cloudinary no pudo eliminar {public_id}: {status or result}")
    return True


def generate_url(public_id, fallback_url=None):
    if not public_id:
        return fallback_url
    configure()
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        secure=True,
        resource_type="image",
        type="upload",
        transformation=[{"quality": "auto", "fetch_format": "auto"}],
    )
    return url or fallback_url


def legacy_path_exists(relative_path):
    from flask import current_app
    if not relative_path:
        return False
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return candidate.is_file()


def local_legacy_path(relative_path):
    from flask import current_app
    if not relative_path:
        return None
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
