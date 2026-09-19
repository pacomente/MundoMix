"""Idempotently migrate legacy MundoMix local images to Cloudinary.

This script never deletes local files. Run it only after the database schema has
been upgraded with Alembic and Cloudinary credentials are configured.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flask import current_app

from app import create_app
from extensions import db
from models import Banner, Category, Product
from services.cloudinary_service import extract_public_id_from_cloudinary_url, upload_image

ROOT = Path(__file__).resolve().parents[1]


def args_parser():
    p = argparse.ArgumentParser(description="MundoMix: migrate local images to Cloudinary")
    p.add_argument("--uploads", default=str(ROOT / "uploads"), help="Legacy uploads directory")
    p.add_argument("--dry-run", action="store_true", help="Validate and report without writing Cloudinary/DB")
    return p.parse_args()


def local_file(raw: str, folder: str, uploads: Path) -> Path | None:
    if not raw or raw.startswith(("http://", "https://")):
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return uploads / candidate


def migrate_main_image(item, folder: str, uploads: Path, dry_run: bool, stats: dict) -> None:
    if not item.image:
        return
    if item.cloudinary_public_id:
        stats["already"] += 1
        return
    extracted = extract_public_id_from_cloudinary_url(item.image)
    if extracted:
        if not dry_run:
            item.cloudinary_public_id = extracted
        stats["already"] += 1
        return
    path = local_file(item.image, folder, uploads)
    if not path or not path.exists():
        stats["errors"] += 1
        print(f"ERROR: {folder}/{item.id}: archivo no encontrado: {item.image}")
        return
    if dry_run:
        stats["found"] += 1
        return
    with path.open("rb") as handle:
        from werkzeug.datastructures import FileStorage
        file = FileStorage(stream=handle, filename=path.name, content_type=None)
        asset = upload_image(file, folder)
    item.image = asset["secure_url"]
    item.cloudinary_public_id = asset["public_id"]
    stats["migrated"] += 1


def migrate_product_extras(product, uploads: Path, dry_run: bool, stats: dict) -> None:
    assets = product.additional_image_assets
    if not assets:
        return
    changed = False
    new_assets = []
    for asset in assets:
        url = asset.get("url")
        public_id = asset.get("public_id")
        if public_id:
            new_assets.append(asset)
            stats["already"] += 1
            continue
        extracted = extract_public_id_from_cloudinary_url(url)
        if extracted:
            new_assets.append({"url": url, "public_id": extracted})
            changed = True
            stats["already"] += 1
            continue
        path = local_file(url, "products", uploads)
        if not path or not path.exists():
            stats["errors"] += 1
            print(f"ERROR: products/{product.id}: adicional no encontrada: {url}")
            new_assets.append(asset)
            continue
        if dry_run:
            stats["found"] += 1
            new_assets.append(asset)
            continue
        with path.open("rb") as handle:
            from werkzeug.datastructures import FileStorage
            file = FileStorage(stream=handle, filename=path.name, content_type=None)
            uploaded = upload_image(file, "products")
        new_assets.append(uploaded)
        changed = True
        stats["migrated"] += 1
    if changed and not dry_run:
        product.set_additional_image_assets(new_assets)


def main() -> int:
    args = args_parser()
    uploads = Path(args.uploads).expanduser()
    if not uploads.is_absolute():
        uploads = (ROOT / uploads).resolve()
    app = create_app()
    stats = {"found": 0, "migrated": 0, "already": 0, "errors": 0}

    with app.app_context():
        changed = False
        for product in Product.query.order_by(Product.id).all():
            before = (product.image, product.cloudinary_public_id)
            migrate_main_image(product, "products", uploads, args.dry_run, stats)
            migrate_product_extras(product, uploads, args.dry_run, stats)
            changed = changed or before != (product.image, product.cloudinary_public_id)
        for category in Category.query.order_by(Category.id).all():
            before = (category.image, category.cloudinary_public_id)
            migrate_main_image(category, "categories", uploads, args.dry_run, stats)
            changed = changed or before != (category.image, category.cloudinary_public_id)
        for banner in Banner.query.order_by(Banner.id).all():
            before = (banner.image, banner.cloudinary_public_id)
            migrate_main_image(banner, "banners", uploads, args.dry_run, stats)
            changed = changed or before != (banner.image, banner.cloudinary_public_id)

        if not args.dry_run and changed:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Cloudinary image migration DB commit failed")
                raise

    print("\nMIGRACIÓN DE IMÁGENES A CLOUDINARY")
    print("==================================")
    print(f"Encontradas/validadas: {stats['found']}")
    print(f"Migradas:             {stats['migrated']}")
    print(f"Ya migradas:          {stats['already']}")
    print(f"Errores:              {stats['errors']}")
    print(f"Dry-run:              {'sí' if args.dry_run else 'no'}")
    print("Archivos locales:      NO eliminados")
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
