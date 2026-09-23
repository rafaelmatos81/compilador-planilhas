from pathlib import Path
from typing import Iterable, Iterator, Optional
from loguru import logger
from ..common.models import ProgressEvent, FileResult
from ..config import settings
from .reader import read_xlsx
from .extractor import extract
from ..identifier.scorer import best_match
from ..catalog.loader import load_catalog
from ..catalog.models import CatalogManifest
from ..common.exceptions import UnreadableFile
from ..learner import layout_signature


def list_xlsx(input_dir: str | Path, recursive: bool = True) -> list[Path]:
    pattern = "**/*.xlsx" if recursive else "*.xlsx"
    # Ignora arquivos temporários de bloqueio do Excel (~$arquivo.xlsx)
    return sorted(p for p in Path(input_dir).glob(pattern) if not p.name.startswith("~$"))


def compile_iter(
    input_dir: str | Path,
    catalog_path: Path | None = None,
    sample: Optional[int] = None,
    recursive: bool = True,
    confidence_threshold: float = settings.confidence_medium,
) -> Iterator[ProgressEvent]:
    """Yield ProgressEvent for each file processed. Caller handles output assembly."""
    files = list_xlsx(input_dir, recursive)
    if sample:
        files = files[:sample]
    logger.info(f"Found {len(files)} .xlsx files in {input_dir}")
    yield from process_files(files, load_catalog(catalog_path), confidence_threshold)


def process_files(
    files: Iterable[Path],
    catalog: CatalogManifest,
    confidence_threshold: float = settings.confidence_medium,
) -> Iterator[ProgressEvent]:
    files = list(files)
    total = len(files)
    for i, path in enumerate(files):
        result = _process_file(path, catalog, confidence_threshold)
        yield ProgressEvent(current=i + 1, total=total, filename=path.name, result=result)


def _process_file(path: Path, catalog, confidence_threshold: float) -> FileResult:
    result = FileResult(path=str(path))
    try:
        tables = read_xlsx(path)
        if not tables:
            result.skipped = True
            result.error = "no readable sheets"
            return result

        best_score = None
        best_table = None
        for table in tables:
            match = best_match(table, catalog)
            if match and (best_score is None or match.confidence > best_score.confidence):
                best_score = match
                best_table = table

        if best_score is None or best_score.confidence < confidence_threshold:
            result.confidence = best_score.confidence if best_score else 0.0
            # Guarda o layout da aba mais provável para agrupar arquivos sem modelo
            layout_table = best_table or max(tables, key=len)
            result.layout_key = layout_signature(layout_table)
            result.sheet_name = layout_table.sheet_name
            logger.warning(f"Unidentified: {path.name} (confidence={result.confidence:.2f})")
            return result

        result.format_id = best_score.format_id
        result.confidence = best_score.confidence
        result.needs_review = best_score.confidence < settings.confidence_high
        result.sheet_name = best_table.sheet_name
        rows = extract(best_table, catalog.get(best_score.format_id))
        for row in rows:
            row.confidence = result.confidence
            row.needs_review = result.needs_review
        result.rows = rows
        result.rows_extracted = len(rows)
        result.sheets_processed = 1
    except UnreadableFile as e:
        result.error = e.reason
        logger.error(f"Unreadable: {path.name}: {e.reason}")
    except Exception as e:
        result.error = str(e)
        logger.error(f"Error processing {path.name}: {e}")
    return result
