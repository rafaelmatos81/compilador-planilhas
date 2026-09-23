from pathlib import Path
import pandas as pd
from loguru import logger


def extract(pdf_path: str | Path) -> tuple[list[pd.DataFrame], bool]:
    """Returns (tables, is_scanned). is_scanned=True if PDF has no extractable text."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed")
        return [], False

    tables: list[pd.DataFrame] = []
    is_scanned = False
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            all_chars = sum(len(p.chars) for p in pdf.pages)
            is_scanned = all_chars == 0
            if is_scanned:
                return [], True
            for page in pdf.pages:
                for t in page.extract_tables() or []:
                    if t and len(t) > 1:
                        try:
                            df = pd.DataFrame(t[1:], columns=t[0])
                            if _acceptable(df):
                                tables.append(df)
                        except Exception:
                            pass
    except Exception as e:
        logger.warning(f"pdfplumber failed on {pdf_path}: {e}")
    return tables, is_scanned


def _acceptable(df: pd.DataFrame) -> bool:
    if df.empty or len(df.columns) < 2:
        return False
    total_cells = len(df) * len(df.columns)
    if total_cells == 0:
        return False
    fill_ratio = df.notna().sum().sum() / total_cells
    return fill_ratio >= 0.5
