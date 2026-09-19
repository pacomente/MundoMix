"""One-time, repeatable migration of legacy uploads/ images to Cloudinary.

The script never deletes local files. Each record is committed only after all of
its required Cloudinary uploads succeed. Re-running it skips resources that
already have a Cloudinary public_id or a Cloudinary URL.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.datastructures import FileStorage

from app import create_app
from extensions import db
from models import Product, Category, Banner
from services.cloudinary_service import upload_image, delete_image


ROOT = Path(__file__).resolve().parents[1]


def is_cloudinary_url(value: str | None) -> bool:
    return bool(value and "res.cloudinary.com/" in value and "/image/upload/" in value)


def cloudinary_public_id_from_url(value: str | None) -> str | None:
    if not is_cloudinary_url(value):
        return None
    path = urlparse(value).path
    marker = "/image/upload/"
    if marker not in path:
        return None
    tail = path.split(marker, 1)[1].lstrip("/")
    parts = tail.split("/")
    if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
        parts = parts[1:]
    if not parts:
        return None
    filename = parts[-1]
    public_name = filename.rsplit(".", 1)[0]
    return "/".join(parts[:-1] + [public_name])


def legacy_path(root: Path, stored: str) -> Path:
    stored = stored.replace("\\", "/").lstrip("/")
    return root / "uploads" / stored


def upload_legacy(root: Path, stored: str, folder: str, public_id_hint: str) -> dict:
    path = legacy_path(root, stored)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo local: {path}")
    with path.open("rb") as handle:
        fs = FileStorage(stream=handle, filename=path.name, content_type=None)
        return upload_image(fs, folder, public_id=public_id_hint)


def migrate_product(root: Path, product: Product) -> tuple[int, int]:
    migrated = 0
    already = 0
    uploaded = []
    try:
        if product.image:
            if product.cloudinary_public_id and is_cloudinary_url(product.image):
                already += 1
            elif is_cloudinary_url(product.image):
                pid = cloudinary_public_id_from_url(product.image)
                if pid:
                    product.cloudinary_public_id = pid
                    db.session.commit()
                    already += 1
                else:
                    raise RuntimeError(f"No se pudo obtener public_id de {product.image}")
            else:
                result = upload_legacy(root, product.image, "mundomix/products", f"product-{product.id}-main-migrated")
                uploaded.append(result)
                product.image = result["secure_url"]
                product.cloudinary_public_id = result["public_id"]
                migrated += 1

        urls = product.image_list
        public_ids = product.additional_public_id_list
        if len(public_ids) == len(urls) and all(public_ids):
            already += len(urls)
        else:
            new_urls, new_ids = [], []
            for index, stored in enumerate(urls):
                if index < len(public_ids) and public_ids[index] and is_cloudinary_url(stored):
                    new_urls.append(stored)
                    new_ids.append(public_ids[index])
                    already += 1
                    continue
                if is_cloudinary_url(stored):
                    pid = cloudinary_public_id_from_url(stored)
                    if not pid:
                        raise RuntimeError(f"No se pudo obtener public_id de {stored}")
                    new_urls.append(stored)
                    new_ids.append(pid)
                    already += 1
                    continue
                result = upload_legacy(root, stored, "mundomix/products", f"product-{product.id}-extra-{index}-migrated")
                uploaded.append(result)
                new_urls.append(result["secure_url"])
                new_ids.append(result["public_id"])
                migrated += 1
            product.additional_images = ",".join(new_urls)
            product.additional_image_public_ids = json.dumps(new_ids)

        db.session.commit()
        return migrated, already
    except Exception:
        db.session.rollback()
        for result in uploaded:
            try:
                delete_image(result["public_id"])
            except Exception:
                pass
        raise


def migrate_simple(root: Path, item, field: str, public_field: str, folder: str, kind: str) -> tuple[int, int]:
    value = getattr(item, field)
    if not value:
        return 0, 0
    public_id = getattr(item, public_field)
    if public_id and is_cloudinary_url(value):
        return 0, 1
    if is_cloudinary_url(value):
        parsed = cloudinary_public_id_from_url(value)
        if not parsed:
            raise RuntimeError(f"No se pudo obtener public_id de {value}")
        setattr(item, public_field, parsed)
        db.session.commit()
        return 0, 1
    uploaded = []
    try:
        result = upload_legacy(root, value, folder, f"{kind}-{item.id}-migrated")
        uploaded.append(result)
        setattr(item, field, result["secure_url"])
        setattr(item, public_field, result["public_id"])
        db.session.commit()
        return 1, 0
    except Exception:
        db.session.rollback()
        for result in uploaded:
            try:
                delete_image(result["public_id"])
            except Exception:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(description="Migrar imágenes legacy de MundoMix a Cloudinary.")
    parser.add_argument("--root", default=str(ROOT), help="Raíz del proyecto que contiene uploads/")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    app = create_app()
    with app.app_context():
        counts = {"products": 0, "categories": 0, "banners": 0, "additional": 0, "already": 0, "errors": 0}

        products = Product.query.order_by(Product.id).all()
        categories = Category.query.order_by(Category.id).all()
        banners = Banner.query.order_by(Banner.id).all()

        for item in products:
            try:
                migrated, already = migrate_product(root, item)
                counts["products"] += migrated
                counts["already"] += already
                counts["additional"] += max(0, len(item.additional_public_id_list))
            except Exception as exc:
                counts["errors"] += 1
                print(f"[ERROR] product {item.id}: {exc}")

        for item in categories:
            try:
                migrated, already = migrate_simple(root, item, "image", "cloudinary_public_id", "mundomix/categories", "category")
                counts["categories"] += migrated
                counts["already"] += already
            except Exception as exc:
                counts["errors"] += 1
                print(f"[ERROR] category {item.id}: {exc}")

        for item in banners:
            try:
                migrated, already = migrate_simple(root, item, "image", "cloudinary_public_id", "mundomix/banners", "banner")
                counts["banners"] += migrated
                counts["already"] += already
            except Exception as exc:
                counts["errors"] += 1
                print(f"[ERROR] banner {item.id}: {exc}")

        print("\n=== Migración Cloudinary ===")
        print(f"Productos encontrados: {len(products)}")
        print(f"Categorías encontradas: {len(categories)}")
        print(f"Banners encontrados: {len(banners)}")
        print(f"Productos migrados: {counts['products']}")
        print(f"Categorías migradas: {counts['categories']}")
        print(f"Banners migrados: {counts['banners']}")
        print(f"Imágenes adicionales procesadas: {counts['additional']}")
        print(f"Ya migrados: {counts['already']}")
        print(f"Errores: {counts['errors']}")

        if counts["errors"]:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
