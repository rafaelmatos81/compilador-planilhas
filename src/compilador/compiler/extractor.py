from ..common.models import ParsedTable, CanonicalRow
from ..catalog.models import FormatEntry
from ..identifier.normalizer import normalize, find_header_row_index


def extract(table: ParsedTable, fmt: FormatEntry) -> list[CanonicalRow]:
    """Extract canonical rows from a table using format extraction rules."""
    if not fmt:
        return []
    rows = table.rows
    header_idx = fmt.extraction.header_row - 1
    data_start = fmt.extraction.data_start_row - 1

    if header_idx >= len(rows):
        header_idx = find_header_row_index(rows)
        data_start = header_idx + 1

    header = rows[header_idx] if header_idx < len(rows) else []
    col_map = _build_col_map(header, fmt.extraction.column_map)
    skip = [normalize(s) for s in fmt.extraction.skip_rows_containing]

    canonical_rows = []
    for row_idx, row in enumerate(rows[data_start:], start=data_start + 1):
        if _should_skip(row, skip):
            continue
        if not any(c.strip() for c in row):
            continue
        data = {
            canonical_field: row[col_idx] if col_idx < len(row) else ""
            for canonical_field, col_idx in col_map.items()
        }
        canonical_rows.append(CanonicalRow(
            source_file=table.source_file,
            source_sheet=table.sheet_name,
            format_id=fmt.format_id,
            confidence=0.0,
            ocr_used=False,
            needs_review=False,
            row_index_in_source=row_idx,
            data=data,
        ))
    return canonical_rows


def _build_col_map(header: list[str], column_map: dict[str, str]) -> dict[str, int]:
    result = {}
    for canonical, source_name in column_map.items():
        norm_source = normalize(source_name)
        for idx, cell in enumerate(header):
            if normalize(cell) == norm_source:
                result[canonical] = idx
                break
    return result


def _should_skip(row: list[str], skip_normalized: list[str]) -> bool:
    if not skip_normalized or not row:
        return False
    first_cell = normalize(row[0])
    return any(s in first_cell for s in skip_normalized)
