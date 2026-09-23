from pathlib import Path
import re
import pandas as pd
from loguru import logger


def extract(pdf_path: str | Path, lang: str = "por", dpi: int = 300) -> list[pd.DataFrame]:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.warning("pdf2image/pytesseract not installed — OCR unavailable")
        return []

    tables: list[pd.DataFrame] = []
    try:
        images = convert_from_path(str(pdf_path), dpi=dpi)
        for img in images:
            text = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
            df = _text_to_dataframe(text)
            if df is not None:
                tables.append(df)
    except Exception as e:
        logger.warning(f"OCR failed on {pdf_path}: {e}")
    return tables


def _text_to_dataframe(text: str) -> pd.DataFrame | None:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    rows = [re.split(r"\s{2,}|\t", line) for line in lines]
    max_cols = max(len(r) for r in rows)
    if max_cols < 2:
        return None
    padded = [r + [""] * (max_cols - len(r)) for r in rows]
    df = pd.DataFrame(padded[1:], columns=padded[0])
    return df if len(df) >= 1 else None
