"""One-shot, repeatable migration of legacy MundoMix images to Cloudinary.

Usage:
    python scripts/migrate_images_to_cloudinary.py

The script never deletes legacy files. It uploads first, then commits the
Cloudinary URL/public_id to PostgreSQL. Already migrated rows are skipped.
Failures are logged and processing continues.
"""
import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from flask import current_app

from app import create_app
from extensions import db
from models import Product, Category, Banner
from models.restaurant import Restaurant, RestaurantProduct
from services.cloudinary_service import upload_image, cloudinary, generate_url


def is_cloudinary_url(value):
    return bool(value and "res.cloudinary.com" in value)


def migrate_local(relative_path, folder, public_id):
    if not relative_path:
        return None
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise RuntimeError(f"Ruta de imagen fuera de UPLOAD_FOLDER: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open("rb") as fh:
        class F:
            filename = path.name
            stream = fh
        try:
            return upload_image(F(), folder, public_id=public_id)
        except Exception as exc:
            if "already exists" in str(exc).lower() or "already_exists" in str(exc).lower():
                return {"secure_url": generate_url(f"{folder}/{public_id}"), "public_id": f"{folder}/{public_id}"}
            raise


def migrate_url(url, folder, public_id):
    # Cloudinary can fetch a public remote image URL directly. This path is
    # intentionally used only for legacy external URLs, never for new uploads.
    from services.cloudinary_service import configure
    configure()
    try:
        result = cloudinary.uploader.upload(url, folder=folder, public_id=public_id, overwrite=False, resource_type="image", unique_filename=False, invalidate=True)
        return {"secure_url": result.get("secure_url") or result.get("url"), "public_id": result.get("public_id")}
    except Exception as exc:
        if "already exists" in str(exc).lower() or "already_exists" in str(exc).lower():
            pid = f"{folder}/{public_id}"
            return {"secure_url": generate_url(pid), "public_id": pid}
        raise


def migrate_ref(legacy, folder, public_id):
    if not legacy:
        return None
    if is_cloudinary_url(legacy):
        return {"secure_url": legacy, "public_id": None}
    if str(legacy).startswith(("http://", "https://")):
        return migrate_url(legacy, folder, public_id)
    return migrate_local(legacy, folder, public_id)


def migrate_model(obj, legacy_attr, url_attr, id_attr, folder, public_id):
    current_url = getattr(obj, url_attr)
    current_id = getattr(obj, id_attr)
    if current_url and current_id:
        return "already"
    legacy = getattr(obj, legacy_attr)
    if not legacy:
        return "empty"
    result = migrate_ref(legacy, folder, public_id)
    if not result:
        return "empty"
    # A Cloudinary URL already stored in the legacy column can be adopted as
    # a URL without pretending we know its public_id.
    setattr(obj, url_attr, result["secure_url"])
    if result.get("public_id"):
        setattr(obj, id_attr, result["public_id"])
    db.session.commit()
    return "migrated"


def migrate_additional(product, stats):
    legacy = product.additional_images or ""
    if not legacy or product.additional_image_public_ids:
        stats["already"] += 1 if product.additional_image_public_ids else 0
        return
    urls, ids = [], []
    for index, value in enumerate([x for x in legacy.split(",") if x]):
        try:
            result = migrate_ref(value, "mundomix/products", f"product-{product.id}-extra-{index}")
            if result:
                urls.append(result["secure_url"]); ids.append(result.get("public_id") or "")
                stats["migrated"] += 1
        except Exception as exc:
            stats["failed"] += 1
            stats["errors"].append(f"Product {product.id} additional[{index}]: {exc}")
    if urls:
        product.additional_image_urls = ",".join(urls)
        product.additional_image_public_ids = ",".join(ids)
        db.session.commit()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limitar cantidad por modelo (0 = todos)")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        stats = {"found": 0, "migrated": 0, "already": 0, "failed": 0, "errors": []}
        collections = [
            (Product, "image", "image_url", "cloudinary_public_id", "mundomix/products", "product-{id}"),
            (Category, "image", "image_url", "cloudinary_public_id", "mundomix/categories", "category-{id}"),
            (Banner, "image", "image_url", "cloudinary_public_id", "mundomix/banners", "banner-{id}"),
            (Restaurant, "logo", "logo_url", "logo_cloudinary_public_id", "mundomix/restaurants/{id}", "restaurant-{id}-logo"),
            (Restaurant, "banner", "banner_url", "banner_cloudinary_public_id", "mundomix/restaurants/{id}", "restaurant-{id}-banner"),
            (RestaurantProduct, "image", "image_url", "cloudinary_public_id", "mundomix/restaurants/{restaurant_id}/products", "restaurant-{restaurant_id}-product-{id}"),
        ]
        for model, legacy_attr, url_attr, id_attr, folder_tpl, public_tpl in collections:
            query = model.query.order_by(model.id)
            if args.limit: query = query.limit(args.limit)
            for obj in query.all():
                legacy = getattr(obj, legacy_attr)
                if not legacy:
                    continue
                stats["found"] += 1
                if getattr(obj, url_attr) and getattr(obj, id_attr):
                    stats["already"] += 1; continue
                folder = folder_tpl.format(id=getattr(obj, "id"), restaurant_id=getattr(obj, "restaurant_id", ""))
                public_id = public_tpl.format(id=getattr(obj, "id"), restaurant_id=getattr(obj, "restaurant_id", ""))
                try:
                    status = migrate_model(obj, legacy_attr, url_attr, id_attr, folder, public_id)
                    if status == "migrated": stats["migrated"] += 1
                    elif status == "already": stats["already"] += 1
                except Exception as exc:
                    db.session.rollback(); stats["failed"] += 1
                    stats["errors"].append(f"{model.__name__} {obj.id} {legacy_attr}: {exc}")
            if model is Product:
                for product in query.all():
                    migrate_additional(product, stats)
        print(f"total encontradas: {stats['found']}")
        print(f"total migradas: {stats['migrated']}")
        print(f"total ya migradas: {stats['already']}")
        print(f"total fallidas: {stats['failed']}")
        for error in stats["errors"]:
            print(f"ERROR: {error}")


if __name__ == "__main__":
    run()
