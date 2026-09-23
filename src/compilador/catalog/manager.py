from pathlib import Path
from .loader import load_catalog, append_format, load_format_from_file
from .models import FormatEntry, CatalogManifest
from ..common.exceptions import CatalogError


def list_formats(catalog_path: Path | None = None) -> list[FormatEntry]:
    return load_catalog(catalog_path).formats


def inspect_format(format_id: str, catalog_path: Path | None = None) -> FormatEntry:
    catalog = load_catalog(catalog_path)
    entry = catalog.get(format_id)
    if not entry:
        raise CatalogError(f"Format '{format_id}' not found in catalog")
    return entry


def add_format_from_file(json_path: Path | str, catalog_path: Path | None = None) -> CatalogManifest:
    entry = load_format_from_file(json_path)
    return append_format(entry, catalog_path)


def validate_catalog(catalog_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_catalog(catalog_path)
        seen_ids: set[str] = set()
        for fmt in catalog.formats:
            if fmt.format_id in seen_ids:
                errors.append(f"Duplicate format_id: {fmt.format_id}")
            seen_ids.add(fmt.format_id)
    except Exception as e:
        errors.append(str(e))
    return errors
