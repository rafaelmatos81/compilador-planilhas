from rapidfuzz import fuzz
from ..catalog.models import CatalogManifest, FormatEntry, HeaderAnchor, ColumnAnchor, CellAnchor
from ..common.models import ParsedTable, ScoredMatch
from .normalizer import normalize, normalize_row, find_header_row_index


def score_all(table: ParsedTable, catalog: CatalogManifest) -> list[ScoredMatch]:
    """Score table against all catalog entries. Returns sorted list (highest first)."""
    norm_rows = [normalize_row(row) for row in table.rows]
    results = [_score_entry(norm_rows, entry) for entry in catalog.formats]
    # Em empate, vence o modelo que casou mais âncoras (o mais específico)
    results.sort(key=lambda m: (m.confidence, len(m.matched_anchors)), reverse=True)
    return results


def best_match(table: ParsedTable, catalog: CatalogManifest) -> ScoredMatch | None:
    matches = score_all(table, catalog)
    return matches[0] if matches else None


def best_match_among(
    tables: list[ParsedTable], catalog: CatalogManifest
) -> tuple[ScoredMatch | None, ParsedTable | None]:
    """Score every table/sheet from a file and return the best match with its table.

    Usado quando um arquivo produz mais de uma tabela (abas de planilha, ou múltiplas
    tabelas extraídas de um PDF) e não se sabe de antemão qual delas casa com um modelo.
    """
    best_score, best_table = None, None
    for table in tables:
        match = best_match(table, catalog)
        if match and (best_score is None or match.confidence > best_score.confidence):
            best_score, best_table = match, table
    return best_score, best_table


def _score_entry(norm_rows: list[list[str]], entry: FormatEntry) -> ScoredMatch:
    earned = 0.0
    max_possible = 0.0
    matched: list[str] = []

    for anchor in entry.detection.header_anchors:
        max_possible += anchor.weight
        score = _score_header_anchor(norm_rows, anchor)
        if anchor.required and score == 0:
            return ScoredMatch(format_id=entry.format_id, confidence=0.0)
        if score > 0:
            matched.append(f"header:{anchor.text[:20]}")
        earned += anchor.weight * score

    if entry.detection.column_anchors:
        # A linha de cabeçalho pode variar entre arquivos do mesmo modelo: testa a
        # detectada automaticamente e a configurada no modelo, e fica com a melhor.
        candidates = {find_header_row_index(norm_rows)}
        configured = entry.extraction.header_row - 1
        if 0 <= configured < len(norm_rows):
            candidates.add(configured)
        best = None
        for idx in sorted(candidates):
            header_row = norm_rows[idx] if idx < len(norm_rows) else []
            cand = _score_columns(entry.detection.column_anchors, header_row)
            if best is None or (not cand[3], cand[0]) > (not best[3], best[0]):
                best = cand
        col_earned, col_max, col_matched, col_missing = best
        if col_missing:
            return ScoredMatch(format_id=entry.format_id, confidence=0.0)
        earned += col_earned
        max_possible += col_max
        matched += col_matched

    for anchor in entry.detection.cell_anchors:
        max_possible += anchor.weight
        score = _score_cell_anchor(norm_rows, anchor)
        if score > 0:
            matched.append(f"cell:{anchor.text[:20]}")
        earned += anchor.weight * score

    hints = entry.detection.structure_hints
    if norm_rows and hints.min_columns and len(norm_rows[0]) >= hints.min_columns:
        earned += 0.05
    if hints.min_data_rows and len(norm_rows) >= hints.min_data_rows:
        earned += 0.05

    if max_possible == 0:
        return ScoredMatch(format_id=entry.format_id, confidence=0.0)

    confidence = min(1.0, earned / max_possible)
    return ScoredMatch(format_id=entry.format_id, confidence=confidence, matched_anchors=matched)


def _score_columns(
    anchors: list[ColumnAnchor], header_row: list[str]
) -> tuple[float, float, list[str], bool]:
    """Returns (earned, max_possible, matched, missing_required)."""
    earned = max_possible = 0.0
    matched: list[str] = []
    missing = False
    for anchor in anchors:
        max_possible += anchor.weight
        score = _score_column_anchor(header_row, anchor)
        if anchor.required and score == 0:
            missing = True
        if score > 0:
            matched.append(f"col:{anchor.canonical_name}")
        earned += anchor.weight * score
    return earned, max_possible, matched, missing


def _score_header_anchor(norm_rows: list[list[str]], anchor: HeaderAnchor) -> float:
    norm_text = normalize(anchor.text)
    scan_rows = norm_rows[:anchor.first_N] if anchor.scope == "first_N_rows" else norm_rows
    for row in scan_rows:
        for cell in row:
            s = _match(cell, norm_text, anchor.match_mode, 85)
            if s > 0:
                return s
    return 0.0


def _score_column_anchor(header_row: list[str], anchor: ColumnAnchor) -> float:
    best = 0.0
    for alias in anchor.aliases:
        norm_alias = normalize(alias)
        for cell in header_row:
            score = fuzz.token_sort_ratio(cell, norm_alias) / 100.0
            if score * 100 >= anchor.fuzzy_threshold:
                best = max(best, score)
    return best


def _score_cell_anchor(norm_rows: list[list[str]], anchor: CellAnchor) -> float:
    norm_text = normalize(anchor.text)
    rows_to_check = norm_rows
    if anchor.row is not None:
        idx = anchor.row - 1
        rows_to_check = [norm_rows[idx]] if idx < len(norm_rows) else []
    for row in rows_to_check:
        cells_to_check = row
        if anchor.col is not None:
            idx = anchor.col - 1
            cells_to_check = [row[idx]] if idx < len(row) else []
        for cell in cells_to_check:
            s = _match(cell, norm_text, anchor.match_mode, 85)
            if s > 0:
                return s
    return 0.0


def _match(cell: str, norm_text: str, mode: str, fuzzy_threshold: int) -> float:
    if mode == "exact":
        return 1.0 if cell == norm_text else 0.0
    if mode == "contains":
        return 1.0 if norm_text in cell else 0.0
    if mode == "fuzzy":
        ratio = fuzz.partial_ratio(cell, norm_text)
        return ratio / 100.0 if ratio >= fuzzy_threshold else 0.0
    return 0.0
