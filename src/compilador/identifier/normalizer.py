import unicodedata
import re


def normalize(text: str) -> str:
    """Lowercase, remove accents, collapse whitespace."""
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text


def slugify(text: str) -> str:
    """normalize() + tudo que não é alfanumérico vira '_'. Ex.: 'Valor Unit.' -> 'valor_unit'."""
    return re.sub(r"[^a-z0-9]+", "_", normalize(text)).strip("_")


def normalize_row(row: list[str]) -> list[str]:
    return [normalize(str(cell)) for cell in row]


def find_header_row_index(rows: list[list[str]], max_scan: int = 15) -> int:
    """Return index of the row most likely to be the column header."""
    best_idx = 0
    best_score = -1
    for i, row in enumerate(rows[:max_scan]):
        non_empty = [c for c in row if c.strip()]
        alpha_count = sum(1 for c in non_empty if not _is_numeric(c))
        if alpha_count > best_score:
            best_score = alpha_count
            best_idx = i
    return best_idx


def _is_numeric(text: str) -> bool:
    cleaned = text.replace(".", "").replace(",", "").replace("-", "").replace("r$", "").strip()
    return cleaned.isdigit() if cleaned else False
