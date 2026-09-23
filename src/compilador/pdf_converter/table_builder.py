import pandas as pd
from ..common.models import ParsedTable


def dataframe_to_parsed_table(df: pd.DataFrame, source_file: str = "") -> ParsedTable:
    """Convert a DataFrame (from any PDF stage) to ParsedTable for the scorer."""
    rows = [list(df.columns.astype(str))]
    for _, row in df.iterrows():
        rows.append([str(v) if v is not None else "" for v in row])
    return ParsedTable(rows=rows, sheet_name="pdf", source_file=source_file)


def raw_rows_to_parsed_table(raw_rows: list[list[str]], source_file: str = "") -> ParsedTable:
    return ParsedTable(rows=raw_rows, sheet_name="pdf", source_file=source_file)
