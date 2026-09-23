from pathlib import Path
from typing import Iterator, Optional
from loguru import logger
from ..common.models import ProgressEvent, FileResult
from .reader import read_xlsx
from .extractor import extract
from ..identifier.scorer import best_match
from ..catalog.loader import load_catalog
from ..common.exceptions import UnreadableFile


def compile_iter(
    input_dir: str | Path,
    catalog_path: Path | None = None,
    sample: Optional[int] = None,
    recursive: bool = True,
    confidence_threshold: float = 0.40,
) -> Iterator[ProgressEvent]:
    """Yield ProgressEvent for each file processed. Caller handles output assembly."""
    catalog = load_catalog(catalog_path)
    input_dir = Path(input_dir)
    pattern = "**/*.xlsx" if recursive else "*.xlsx"
    files = sorted(input_dir.glob(pattern))
    if sample:
        files = files[:sample]
    total = len(files)
    logger.info(f"Found {total} .xlsx files in {input_dir}")

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
            logger.warning(f"Unidentified: {path.name} (confidence={result.confidence:.2f})")
            return result

        result.format_id = best_score.format_id
        result.confidence = best_score.confidence
        result.needs_review = best_score.confidence < 0.85
        rows = extract(best_table, catalog.get(best_score.format_id))
        result.rows_extracted = len(rows)
        result.sheets_processed = 1
        result._canonical_rows = rows  # type: ignore[attr-defined]
    except UnreadableFile as e:
        result.error = e.reason
        logger.error(f"Unreadable: {path.name}: {e.reason}")
    except Exception as e:
        result.error = str(e)
        logger.error(f"Error processing {path.name}: {e}")
    return result
