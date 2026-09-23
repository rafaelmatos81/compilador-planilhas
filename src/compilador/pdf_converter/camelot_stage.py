from pathlib import Path
import pandas as pd
from loguru import logger


def extract(pdf_path: str | Path) -> list[pd.DataFrame]:
    try:
        import camelot
    except ImportError:
        logger.warning("camelot-py not installed, skipping stage 2")
        return []

    for flavor in ("lattice", "stream"):
        try:
            result = camelot.read_pdf(str(pdf_path), flavor=flavor, pages="all")
            tables = [t.df for t in result if t.parsing_report.get("accuracy", 0) >= 70]
            if tables:
                logger.debug(f"camelot {flavor}: {len(tables)} tables from {Path(pdf_path).name}")
                return tables
        except Exception as e:
            logger.debug(f"camelot {flavor} failed: {e}")
    return []
