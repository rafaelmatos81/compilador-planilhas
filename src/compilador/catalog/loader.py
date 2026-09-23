import json
from pathlib import Path
from datetime import date
from loguru import logger
from .models import CatalogManifest, FormatEntry
from ..common.exceptions import CatalogError

_DEFAULT_CATALOG = Path(__file__).parent.parent.parent.parent / "catalog" / "formats.json"


def load_catalog(path: Path | str | None = None) -> CatalogManifest:
    catalog_path = Path(path) if path else _DEFAULT_CATALOG
    if not catalog_path.exists():
        logger.warning(f"Catalog not found at {catalog_path}, returning empty catalog")
        return CatalogManifest()
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        return CatalogManifest.model_validate(data)
    except Exception as e:
        raise CatalogError(f"Failed to load catalog from {catalog_path}: {e}") from e


def save_catalog(catalog: CatalogManifest, path: Path | str | None = None) -> None:
    catalog_path = Path(path) if path else _DEFAULT_CATALOG
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.last_updated = str(date.today())
    catalog_path.write_text(
        json.dumps(catalog.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Catalog saved to {catalog_path} ({len(catalog.formats)} formats)")


def append_format(entry: FormatEntry, path: Path | str | None = None) -> CatalogManifest:
    catalog = load_catalog(path)
    if entry.format_id in catalog.ids():
        raise CatalogError(f"format_id '{entry.format_id}' already exists in catalog")
    catalog.formats.append(entry)
    save_catalog(catalog, path)
    return catalog


def load_format_from_file(json_path: Path | str) -> FormatEntry:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return FormatEntry.model_validate(data)
