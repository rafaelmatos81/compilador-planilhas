import re
from ..common.models import ParsedTable, CanonicalRow
from ..catalog.models import FormatEntry
from ..identifier.normalizer import normalize, find_header_row_index

_HEADER_SCAN_ROWS = 30


def extract(table: ParsedTable, fmt: FormatEntry) -> list[CanonicalRow]:
    """Extract canonical rows from a table using format extraction rules."""
    if not fmt:
        return []
    rows = table.rows
    header_idx = _locate_header(rows, fmt)
    offset = max(1, fmt.extraction.data_start_row - fmt.extraction.header_row)
    data_start = header_idx + offset

    header = rows[header_idx] if header_idx < len(rows) else []
    col_map = _build_col_map(header, fmt.extraction.column_map)
    skip = [normalize(s) for s in fmt.extraction.skip_rows_containing]

    canonical_rows = []
    for row_idx, row in enumerate(rows[data_start:], start=data_start + 1):
        if _should_skip(row, skip):
            continue
        data = {
            canonical_field: row[col_idx] if col_idx < len(row) else ""
            for canonical_field, col_idx in col_map.items()
        }
        if not any(str(v).strip() for v in data.values()):
            continue
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


def _locate_header(rows: list[list[str]], fmt: FormatEntry) -> int:
    """Linha de cabeçalho (0-based): a que contém mais colunas do modelo.

    A linha configurada no modelo vence empates, então arquivos onde o cabeçalho
    deslocou algumas linhas continuam sendo lidos corretamente.
    """
    wanted = {normalize(split_occurrence(src)[0]) for src in fmt.extraction.column_map.values()}
    configured = fmt.extraction.header_row - 1
    best_idx, best_key = -1, (0, False)
    for i, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        cells = {normalize(c) for c in row}
        key = (len(wanted & cells), i == configured)
        if key > best_key:
            best_idx, best_key = i, key
    if best_idx >= 0:
        return best_idx
    if 0 <= configured < len(rows):
        return configured
    return find_header_row_index(rows)


def split_occurrence(source_name: str) -> tuple[str, int]:
    """'Valor #2' -> ('Valor', 2): 2ª coluna com esse título. Sem sufixo -> 1ª."""
    m = re.match(r"^(.*?)\s*#(\d+)$", source_name)
    return (m.group(1), int(m.group(2))) if m else (source_name, 1)


def _build_col_map(header: list[str], column_map: dict[str, str]) -> dict[str, int]:
    result = {}
    for canonical, source_name in column_map.items():
        base, nth = split_occurrence(source_name)
        norm_source = normalize(base)
        seen = 0
        for idx, cell in enumerate(header):
            if normalize(cell) == norm_source:
                seen += 1
                if seen == nth:
                    result[canonical] = idx
                    break
    return result


def _should_skip(row: list[str], skip_normalized: list[str]) -> bool:
    if not skip_normalized or not row:
        return False
    first_cell = normalize(row[0])
    return any(s in first_cell for s in skip_normalized)
