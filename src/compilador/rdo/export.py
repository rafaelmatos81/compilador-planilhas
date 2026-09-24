"""Exportação do(s) RDO(s) revisados para Excel.

Mesmo formato de workbook da skill `exxata-rdo-extractor` (references/contracts.md):
abas "Resumo RDOs", "Equipamentos", "Mão de Obra Direta", "Mão de Obra Indireta",
"Atividades" e "Observações" — trocando de skill para cá não deveria exigir que
quem recebe a planilha reaprenda nada.
"""
import io
from pathlib import Path
from typing import Any
from openpyxl import Workbook
from .models import RdoRecord


def _append_sheet(workbook: Workbook, sheet_name: str, headers: list[str], rows: list[dict[str, Any]]) -> None:
    ws = workbook.create_sheet(title=sheet_name)
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])


def _pluviometria_ou_vazio(clima, periodo: str):
    valor = getattr(clima, f"pluviometria_{periodo}")
    condicao = (getattr(clima, periodo) or "").strip()
    if not condicao and (not valor):
        return ""
    return valor


def build_rdo_workbook(records: list[RdoRecord]) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)

    summary_headers = [
        "numero_rdo", "data_rdo", "local_obra", "horario_trabalho", "contratante", "contratada",
        "clima_manha", "clima_tarde", "clima_noite",
        "pluviometria_manha", "pluviometria_tarde", "pluviometria_noite",
        "total_mao_de_obra_direta", "total_mao_de_obra_indireta", "total_mao_de_obra",
        "arquivo_origem", "paginas_origem",
    ]
    summary_rows = []
    for r in records:
        total_direta = sum(item.quantidade for item in r.mao_de_obra_direta)
        total_indireta = sum(item.quantidade for item in r.mao_de_obra_indireta)
        summary_rows.append({
            "numero_rdo": r.numero_rdo,
            "data_rdo": r.data_rdo,
            "local_obra": r.local_obra,
            "horario_trabalho": r.horario_trabalho,
            "contratante": r.contratante,
            "contratada": r.contratada,
            "clima_manha": r.clima.manha,
            "clima_tarde": r.clima.tarde,
            "clima_noite": r.clima.noite,
            "pluviometria_manha": _pluviometria_ou_vazio(r.clima, "manha"),
            "pluviometria_tarde": _pluviometria_ou_vazio(r.clima, "tarde"),
            "pluviometria_noite": _pluviometria_ou_vazio(r.clima, "noite"),
            "total_mao_de_obra_direta": total_direta,
            "total_mao_de_obra_indireta": total_indireta,
            "total_mao_de_obra": total_direta + total_indireta,
            "arquivo_origem": r.source_file,
            "paginas_origem": r.source_pages,
        })
    _append_sheet(wb, "Resumo RDOs", summary_headers, summary_rows)

    detailed_specs = [
        ("Equipamentos", ["nome", "empresa", "quantidade"], "equipamentos"),
        ("Mão de Obra Direta", ["funcao", "empresa", "quantidade"], "mao_de_obra_direta"),
        ("Mão de Obra Indireta", ["funcao", "empresa", "quantidade"], "mao_de_obra_indireta"),
        ("Atividades", ["secao", "item", "descricao", "empresa"], "atividades"),
        ("Observações", ["autor", "descricao", "empresa"], "observacoes"),
    ]
    for sheet_name, headers, attr in detailed_specs:
        sheet_headers = ["numero_rdo", "data_rdo", *headers]
        rows = []
        for r in records:
            for item in getattr(r, attr):
                row = {"numero_rdo": r.numero_rdo, "data_rdo": r.data_rdo}
                row.update({h: getattr(item, h) for h in headers})
                rows.append(row)
        _append_sheet(wb, sheet_name, sheet_headers, rows)

    return wb


def export_rdo_workbook_bytes(records: list[RdoRecord], output_path: Path | str | None = None) -> bytes:
    wb = build_rdo_workbook(records)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    data = buf.read()
    if output_path:
        Path(output_path).write_bytes(data)
    return data
