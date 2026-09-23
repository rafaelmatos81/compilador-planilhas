from pathlib import Path
import openpyxl
from loguru import logger
from ..common.models import ParsedTable
from ..common.exceptions import UnreadableFile


def read_xlsx(path: Path) -> list[ParsedTable]:
    """Read all sheets from an xlsx file. Returns list of ParsedTable (one per sheet)."""
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as e:
        raise UnreadableFile(str(path), str(e)) from e

    tables = []
    for sheet_name in wb.sheetnames:
        try:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([str(cell) if cell is not None else "" for cell in row])
            if _has_content(rows):
                tables.append(ParsedTable(rows=rows, sheet_name=sheet_name, source_file=str(path)))
        except Exception as e:
            logger.warning(f"Cannot read sheet '{sheet_name}' in {path.name}: {e}")
    wb.close()
    return tables


def _has_content(rows: list[list[str]]) -> bool:
    return any(any(cell.strip() for cell in row) for row in rows)
