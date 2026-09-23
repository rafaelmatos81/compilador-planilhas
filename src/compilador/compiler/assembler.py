import io
from pathlib import Path
import pandas as pd
from openpyxl.styles import PatternFill
from ..common.models import CanonicalRow, FileResult


def assemble_output(
    canonical_rows: list[CanonicalRow],
    file_results: list[FileResult],
    output_path: Path | str | None = None,
) -> bytes:
    """Assemble compiled output xlsx. Returns bytes (for Streamlit download)."""
    if canonical_rows:
        records = []
        for r in canonical_rows:
            base = {
                "source_file": Path(r.source_file).name,
                "source_sheet": r.source_sheet,
                "format_id": r.format_id,
                "confidence": round(r.confidence, 3),
                "needs_review": r.needs_review,
                "ocr_used": r.ocr_used,
                "row_index_in_source": r.row_index_in_source,
            }
            base.update(r.data)
            records.append(base)
        df_data = pd.DataFrame(records)
    else:
        df_data = pd.DataFrame()

    log_records = [
        {
            "arquivo": Path(r.path).name,
            "formato": r.format_id or "—",
            "confianca": round(r.confidence, 3),
            "status": r.status,
            "linhas_extraidas": r.rows_extracted,
            "erro": r.error or "",
        }
        for r in file_results
    ]
    df_log = pd.DataFrame(log_records)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_data.to_excel(writer, sheet_name="Dados", index=False)
        df_log.to_excel(writer, sheet_name="Log", index=False)
        _style_log_sheet(writer.book["Log"], file_results)

    output.seek(0)
    result = output.read()
    if output_path:
        Path(output_path).write_bytes(result)
    return result


def _style_log_sheet(ws, file_results: list[FileResult]) -> None:
    GREEN = PatternFill("solid", fgColor="C6EFCE")
    YELLOW = PatternFill("solid", fgColor="FFEB9C")
    RED = PatternFill("solid", fgColor="FFC7CE")
    for i, result in enumerate(file_results, start=2):
        fill = GREEN if result.status == "ok" else YELLOW if result.status == "review" else RED
        for cell in ws[i]:
            cell.fill = fill
