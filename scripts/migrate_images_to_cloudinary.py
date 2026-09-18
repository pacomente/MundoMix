"""Safely migrate legacy MundoMix images to Cloudinary.

Run with the production DATABASE_URL and Cloudinary environment variables set.
The script never deletes legacy files and only deletes a Cloudinary object after
its database reference has been committed successfully.
"""
from __future__ import annotations

from pathlib import Path

from app import create_app
from extensions import db
from models import Product, Category, Banner, Restaurant, RestaurantProduct
from services.cloudinary_service import delete_image, is_external_image, upload_image


ROOT = Path(__file__).resolve().parents[1]


def _legacy_file(value):
    if not value or is_external_image(value):
        return None
    target = (ROOT / "uploads" / value).resolve()
    try:
        target.relative_to((ROOT / "uploads").resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def _storage_asset(path: Path, folder: str):
    # FileStorage is not needed here: upload_image accepts file-like objects,
    # but it also validates filename/mime. Use a tiny compatible adapter.
    from werkzeug.datastructures import FileStorage
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        return upload_image(FileStorage(stream=fh, filename=path.name, content_type=mime), folder)


def migrate_scalar(model, image_attr, public_id_attr, folder):
    total = failed = migrated = 0
    for item in model.query.all():
        value = getattr(item, image_attr, None)
        if not value or is_external_image(value):
            continue
        total += 1
        path = _legacy_file(value)
        if not path:
            failed += 1
            print(f"FAIL {model.__name__}#{item.id}: archivo legado no encontrado: {value}")
            continue
        asset = None
        try:
            asset = _storage_asset(path, folder)
            setattr(item, image_attr, asset.url)
            setattr(item, public_id_attr, asset.public_id)
            db.session.commit()
            migrated += 1
            print(f"OK   {model.__name__}#{item.id}: {value} -> {asset.public_id}")
        except Exception as exc:
            db.session.rollback()
            failed += 1
            if asset:
                try:
                    delete_image(asset.public_id)
                except Exception:
                    print(f"WARN no se pudo limpiar upload Cloudinary {asset.public_id}")
            print(f"FAIL {model.__name__}#{item.id}: {exc}")
    return total, migrated, failed


def migrate_products():
    total = migrated = failed = 0
    for item in Product.query.all():
        # Main image.
        if item.image and not is_external_image(item.image):
            total += 1
            path = _legacy_file(item.image)
            asset = None
            if not path:
                failed += 1; print(f"FAIL Product#{item.id}: archivo legado no encontrado: {item.image}")
            else:
                try:
                    asset = _storage_asset(path, "products")
                    item.image, item.cloudinary_public_id = asset.url, asset.public_id
                    db.session.commit(); migrated += 1
                    print(f"OK   Product#{item.id} principal -> {asset.public_id}")
                except Exception as exc:
                    db.session.rollback(); failed += 1
                    if asset:
                        try: delete_image(asset.public_id)
                        except Exception: pass
                    print(f"FAIL Product#{item.id}: {exc}")
        # Additional images: preserve order and migrate only resolvable entries.
        urls = item.image_list
        ids = item.additional_image_public_id_list
        changed = False
        new_urls, new_ids = [], []
        for idx, value in enumerate(urls):
            if is_external_image(value):
                new_urls.append(value); new_ids.append(ids[idx] if idx < len(ids) else ""); continue
            total += 1
            path = _legacy_file(value)
            if not path:
                failed += 1; new_urls.append(value); new_ids.append(ids[idx] if idx < len(ids) else "")
                print(f"FAIL Product#{item.id} adicional: archivo legado no encontrado: {value}")
                continue
            asset = None
            try:
                asset = _storage_asset(path, "products")
                new_urls.append(asset.url); new_ids.append(asset.public_id); changed = True
                migrated += 1
                print(f"OK   Product#{item.id} adicional -> {asset.public_id}")
            except Exception as exc:
                failed += 1; new_urls.append(value); new_ids.append(ids[idx] if idx < len(ids) else "")
                if asset:
                    try: delete_image(asset.public_id)
                    except Exception: pass
                print(f"FAIL Product#{item.id} adicional: {exc}")
        if changed:
            try:
                item.additional_images = ",".join(new_urls)
                item.additional_image_public_ids = ",".join(new_ids)
                db.session.commit()
            except Exception as exc:
                db.session.rollback(); print(f"FAIL Product#{item.id} guardar adicionales: {exc}")
    return total, migrated, failed


def main():
    app = create_app()
    with app.app_context():
        totals = []
        totals.append(migrate_products())
        for args in [
            (Category, "image", "cloudinary_public_id", "categories"),
            (Banner, "image", "cloudinary_public_id", "banners"),
            (Restaurant, "logo", "logo_cloudinary_public_id", "restaurants/logos"),
            (Restaurant, "banner", "banner_cloudinary_public_id", "restaurants/banners"),
            (RestaurantProduct, "image", "cloudinary_public_id", "restaurants/products"),
        ]:
            totals.append(migrate_scalar(*args))
        total = sum(x[0] for x in totals); migrated = sum(x[1] for x in totals); failed = sum(x[2] for x in totals)
        print(f"\nMIGRACIÓN FINAL: total={total} migrables, migradas={migrated}, fallidas={failed}")
        print("Los archivos legacy no fueron eliminados automáticamente.")


if __name__ == "__main__":
    main()
