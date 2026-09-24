"""Fluxo completo: planilhas de modelos diferentes -> aprender modelos -> compilar em colunas padrão."""
import io
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from compilador.catalog.loader import append_format, load_catalog
from compilador.catalog.schema import load_schema
from compilador.common.models import ParsedTable
from compilador.compiler.assembler import assemble_output
from compilador.compiler.reader import read_xlsx
from compilador.compiler.walker import compile_iter
from compilador.learner import build_format, describe_columns, detect_header_row, suggest_mapping


def _xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def pasta(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    # Modelo A: medição, cabeçalho na linha 3, números como texto brasileiro
    _xlsx(d / "a1.xlsx", [
        ["BOLETIM DE MEDIÇÃO", None, None, None],
        [None, None, None, None],
        ["Item", "Descrição do Serviço", "Un", "Quantidade", "Preço Unitário", "Total"],
        ["1.1", "Escavação", "m3", 10, "1.500,50", "15.005,00"],
        ["1.2", "Aterro", "m3", 5, "20,00", "100,00"],
        ["TOTAL GERAL", None, None, None, None, "15.105,00"],
    ])
    # Mesmo modelo A, mas com o cabeçalho deslocado para a linha 5
    _xlsx(d / "a2.xlsx", [
        ["BOLETIM DE MEDIÇÃO"], ["Contrato 123"], ["Obra X"], [None],
        ["Item", "Descrição do Serviço", "Un", "Quantidade", "Preço Unitário", "Total"],
        ["2.1", "Drenagem", "m", 3, "10,00", "30,00"],
    ])
    # Modelo B: diário, com dois títulos "Valor" repetidos
    _xlsx(d / "b1.xlsx", [
        ["Data", "Atividade", "Equipe", "Valor", "Valor"],
        ["2024-01-05", "Concretagem", "E1", 1, 2],
    ])
    return d


def _resultados(pasta, catalog):
    return {Path(e.result.path).name: e.result for e in compile_iter(pasta, catalog_path=catalog)}


def test_sem_modelos_agrupa_por_layout(pasta, tmp_path):
    res = _resultados(pasta, tmp_path / "cat.json")
    assert all(r.status == "unidentified" for r in res.values())
    assert res["a1.xlsx"].layout_key == res["a2.xlsx"].layout_key
    assert res["a1.xlsx"].layout_key != res["b1.xlsx"].layout_key


def test_arquivo_sem_modelo_ainda_produz_linhas(pasta, tmp_path):
    """Sem nenhum modelo cadastrado, os arquivos são convertidos mesmo assim (cabeçalho e
    mapeamento de colunas automáticos), em vez de ficarem vazios até alguém cadastrar um
    modelo — cadastrar um modelo é só um diferencial, não um pré-requisito."""
    res = _resultados(pasta, tmp_path / "cat.json")
    assert all(r.status == "unidentified" for r in res.values())
    assert all(r.rows_extracted > 0 for r in res.values())

    rows = [row for r in res.values() for row in r.rows]
    assert all(row.needs_review for row in rows)
    assert all(row.format_id == "" for row in rows)

    df = pd.read_excel(io.BytesIO(assemble_output(rows, list(res.values()))), sheet_name="Dados")
    assert len(df) == len(rows)
    # "Descrição do Serviço" é reconhecida automaticamente como a coluna padrão "Descrição"
    assert "Descrição" in df.columns


def test_aprende_modelo_e_reconhece_arquivos_do_mesmo_layout(pasta, tmp_path):
    cat = tmp_path / "cat.json"
    schema = load_schema()
    table = read_xlsx(pasta / "a1.xlsx")[0]
    h = detect_header_row(table)
    assert h == 2

    infos = describe_columns(table, h, schema)
    sugestao = {i.header: i.suggestion for i in infos}
    assert sugestao == {
        "Item": "item", "Descrição do Serviço": "descricao", "Un": "unidade",
        "Quantidade": "qtd_medida", "Preço Unitário": "valor_unit", "Total": "valor_total",
    }

    mapping = {i.index: i.suggestion for i in infos}
    entry = build_format(table, h, mapping, name="Medição Prefeitura", existing_ids=[])
    assert entry.format_id == "medicao_prefeitura"
    append_format(entry, cat)

    res = _resultados(pasta, cat)
    assert res["a1.xlsx"].format_id == "medicao_prefeitura"
    assert res["a1.xlsx"].rows_extracted == 2  # linha TOTAL GERAL ignorada
    assert res["a2.xlsx"].format_id == "medicao_prefeitura"  # cabeçalho deslocado
    assert res["a2.xlsx"].rows_extracted == 1
    assert res["b1.xlsx"].status == "unidentified"


def test_dois_modelos_geram_um_unico_xlsx_com_colunas_padrao(pasta, tmp_path):
    cat = tmp_path / "cat.json"
    schema = load_schema()
    for arquivo, nome in [("a1.xlsx", "Medição A"), ("b1.xlsx", "Diário B")]:
        table = read_xlsx(pasta / arquivo)[0]
        h = detect_header_row(table)
        mapping = suggest_mapping(table.rows[h], schema)
        if nome == "Diário B":
            mapping[3] = "valor_unit"  # 1º "Valor"
            mapping[4] = "valor_total"  # 2º "Valor"
        entry = build_format(table, h, mapping, name=nome, existing_ids=load_catalog(cat).ids())
        append_format(entry, cat)

    resultados = list(_resultados(pasta, cat).values())
    assert all(r.status == "ok" for r in resultados), [(r.path, r.status, r.error) for r in resultados]
    rows = [row for r in resultados for row in r.rows]
    df = pd.read_excel(io.BytesIO(assemble_output(rows, resultados)), sheet_name="Dados", dtype={"Item": str})

    # Colunas padrão primeiro, na ordem do esquema; rastreabilidade depois
    cols = list(df.columns)
    assert cols[:8] == ["Item", "Descrição", "Unidade", "Quantidade", "Valor unitário", "Valor total",
                        "Data", "Atividade"]
    assert "Modelo" in cols and "Arquivo de origem" in cols
    assert set(df["Modelo"]) == {"medicao_a", "diario_b"}

    a = df[df["Arquivo de origem"] == "a1.xlsx"].set_index("Item")
    assert a.loc["1.1", "Valor unitário"] == 1500.50  # número real, não texto
    assert a.loc["1.1", "Valor total"] == 15005.0
    b = df[df["Arquivo de origem"] == "b1.xlsx"].iloc[0]
    assert (b["Valor unitário"], b["Valor total"]) == (1, 2)  # títulos repetidos resolvidos
    assert b["Data"] == pd.Timestamp("2024-01-05")


def test_modelo_mais_especifico_vence_empate(pasta, tmp_path):
    cat = tmp_path / "cat.json"
    schema = load_schema()
    table = read_xlsx(pasta / "a1.xlsx")[0]
    h = detect_header_row(table)
    mapping = suggest_mapping(table.rows[h], schema)
    menor = {i: c for i, c in mapping.items() if c in ("item", "descricao")}
    append_format(build_format(table, h, menor, name="Só item e descrição", existing_ids=[]), cat)
    append_format(build_format(table, h, mapping, name="Completo", existing_ids=load_catalog(cat).ids()), cat)
    assert _resultados(pasta, cat)["a1.xlsx"].format_id == "completo"


def test_build_format_valida_entrada():
    t = ParsedTable(rows=[["A", "B"], ["1", "2"]])
    with pytest.raises(ValueError):
        build_format(t, 0, {}, name="x")
    with pytest.raises(ValueError):
        build_format(t, 0, {0: "item", 1: "item"}, name="x")
    with pytest.raises(ValueError):
        build_format(t, 0, {0: "item"}, name="  ")
