from pathlib import Path
from loguru import logger
from .plumber_stage import extract as plumber_extract
from .camelot_stage import extract as camelot_extract
from .ocr_stage import extract as ocr_extract
from .table_builder import dataframe_to_parsed_table
from ..common.models import ParsedTable


def extract_tables(
    pdf_path: str | Path,
    force_ocr: bool = False,
    ocr_lang: str = "por",
    ocr_dpi: int = 300,
) -> tuple[list[ParsedTable], bool]:
    """
    Returns (tables, ocr_used).
    Pipeline: pdfplumber → camelot → OCR fallback.
    """
    pdf_path = Path(pdf_path)

    if not force_ocr:
        dfs, is_scanned = plumber_extract(pdf_path)
        if dfs and not is_scanned:
            logger.info(f"Stage 1 (pdfplumber): {len(dfs)} tables from {pdf_path.name}")
            return [dataframe_to_parsed_table(df, str(pdf_path)) for df in dfs], False

        if not is_scanned:
            dfs = camelot_extract(pdf_path)
            if dfs:
                logger.info(f"Stage 2 (camelot): {len(dfs)} tables from {pdf_path.name}")
                return [dataframe_to_parsed_table(df, str(pdf_path)) for df in dfs], False

    logger.info(f"Stage 3 (OCR): processing {pdf_path.name}")
    dfs = ocr_extract(pdf_path, lang=ocr_lang, dpi=ocr_dpi)
    return [dataframe_to_parsed_table(df, str(pdf_path)) for df in dfs], True
