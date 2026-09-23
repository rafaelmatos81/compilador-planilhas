"""Aprendizado de modelos: a partir de uma planilha de exemplo, sugere o mapeamento
das colunas de origem para as colunas padrão e monta a entrada do catálogo."""
from dataclasses import dataclass, field
from rapidfuzz import fuzz
from .catalog.models import (
    ColumnAnchor, DetectionRules, ExtractionRules, FormatEntry,
)
from .catalog.schema import CanonicalSchema
from .common.models import ParsedTable
from .identifier.normalizer import normalize, slugify, find_header_row_index

_SAMPLES_PER_COLUMN = 3
_SUGGEST_THRESHOLD = 85
DEFAULT_SKIP_ROWS = ["TOTAL", "SUBTOTAL"]


@dataclass
class ColumnInfo:
    index: int
    header: str
    samples: list[str] = field(default_factory=list)
    suggestion: str | None = None  # nome da coluna padrão sugerida


def detect_header_row(table: ParsedTable) -> int:
    """Índice (0-based) da linha que provavelmente é o cabeçalho."""
    return find_header_row_index(table.rows)


def layout_signature(table: ParsedTable) -> str:
    """Identifica o 'layout' da planilha pelos títulos de coluna; serve para agrupar
    arquivos do mesmo modelo que ainda não foi cadastrado."""
    if not table.rows:
        return ""
    header = table.rows[detect_header_row(table)]
    return "|".join(n for n in (normalize(c) for c in header) if n)


def describe_columns(
    table: ParsedTable, header_idx: int, schema: CanonicalSchema
) -> list[ColumnInfo]:
    """Uma entrada por coluna com título preenchido, com valores de exemplo e sugestão."""
    header = table.rows[header_idx]
    body = table.rows[header_idx + 1:]
    suggestions = suggest_mapping(header, schema)
    infos = []
    for idx, title in enumerate(header):
        if not title.strip():
            continue
        samples = []
        for row in body:
            if idx < len(row) and row[idx].strip():
                samples.append(row[idx].strip())
                if len(samples) == _SAMPLES_PER_COLUMN:
                    break
        infos.append(ColumnInfo(idx, title.strip(), samples, suggestions.get(idx)))
    return infos


def suggest_mapping(header: list[str], schema: CanonicalSchema) -> dict[int, str]:
    """Sugere {índice da coluna: coluna padrão} comparando títulos com nome/rótulo/apelidos.

    Cada coluna de origem e cada coluna padrão é usada no máximo uma vez.
    """
    candidates = []
    for idx, title in enumerate(header):
        norm_title = normalize(title)
        if not norm_title:
            continue
        for f in schema.fields:
            terms = {normalize(t) for t in (f.name.replace("_", " "), f.label, *f.aliases)}
            score = max(fuzz.token_sort_ratio(norm_title, t) for t in terms)
            if score >= _SUGGEST_THRESHOLD:
                candidates.append((score, idx, f.name))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    used_cols: set[int] = set()
    used_fields: set[str] = set()
    result: dict[int, str] = {}
    for _, idx, name in candidates:
        if idx not in used_cols and name not in used_fields:
            result[idx] = name
            used_cols.add(idx)
            used_fields.add(name)
    return result


def build_format(
    table: ParsedTable,
    header_idx: int,
    mapping: dict[int, str],
    *,
    name: str,
    agency: str = "",
    document_type: str = "",
    skip_rows: list[str] | None = None,
    description: str = "",
    existing_ids: list[str] | None = None,
) -> FormatEntry:
    """Monta a entrada do catálogo. `mapping` é {índice da coluna de origem: coluna padrão}."""
    name = name.strip()
    if not name:
        raise ValueError("Informe um nome para o modelo.")
    if not mapping:
        raise ValueError("Mapeie ao menos uma coluna para uma coluna padrão.")
    targets = list(mapping.values())
    if len(targets) != len(set(targets)):
        raise ValueError("Uma coluna padrão foi escolhida para mais de uma coluna de origem.")

    header = table.rows[header_idx]
    column_map: dict[str, str] = {}
    anchors: list[ColumnAnchor] = []
    for idx, canonical in sorted(mapping.items()):
        title = header[idx].strip()
        # Títulos repetidos (ex.: dois "Valor") são distinguidos pela ordem: "Valor #2"
        nth = sum(1 for c in header[: idx + 1] if normalize(c) == normalize(title))
        column_map[canonical] = title if nth == 1 else f"{title} #{nth}"
        anchors.append(ColumnAnchor(
            canonical_name=canonical, aliases=[title], fuzzy_threshold=90, required=True,
        ))

    return FormatEntry(
        format_id=unique_format_id(name, existing_ids or []),
        display_name=name,
        agency=agency.strip() or "Não informado",
        document_type=document_type.strip() or "Planilha",
        version="1.0",
        description=description,
        detection=DetectionRules(column_anchors=anchors),
        extraction=ExtractionRules(
            header_row=header_idx + 1,
            data_start_row=header_idx + 2,
            column_map=column_map,
            skip_rows_containing=skip_rows if skip_rows is not None else list(DEFAULT_SKIP_ROWS),
        ),
    )


def unique_format_id(name: str, existing_ids: list[str]) -> str:
    base = slugify(name) or "modelo"
    candidate, n = base, 2
    while candidate in existing_ids:
        candidate = f"{base}_{n}"
        n += 1
    return candidate
