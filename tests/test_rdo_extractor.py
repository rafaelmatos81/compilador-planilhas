"""Extração heurística de RDO (pré-preenchimento) + exportação para o workbook
padrão (mesmas abas da skill exxata-rdo-extractor)."""
from compilador.rdo.export import build_rdo_workbook
from compilador.rdo.heuristics import classify_and_map_table, guess_header_fields, guess_observacoes
from compilador.rdo.models import RdoRecord, EquipamentoItem, MaoDeObraItem
from compilador.rdo.text_extract import split_into_blocks


_TEXTO_RDO = """RDO. N°: 275
Data: 10/04/2026
Cliente: GERDAU MINERAÇÃO
Contratada: EXXATA ENGENHARIA
Obra: MONTAGEM ELETROMECÂNICA
Horário início: 07:00
Horário término: 17:00
Observações: Equipe trabalhou normalmente durante o turno, sem intercorrências.
Assinatura: ____________
"""


def test_guess_header_fields():
    fields = guess_header_fields(_TEXTO_RDO)
    assert fields["numero_rdo"] == "275"
    assert fields["data_rdo"] == "2026-04-10"  # convertido para AAAA-MM-DD
    assert fields["contratante"] == "GERDAU MINERAÇÃO"
    assert fields["contratada"] == "EXXATA ENGENHARIA"
    assert fields["local_obra"] == "MONTAGEM ELETROMECÂNICA"
    assert fields["horario_trabalho"] == "07:00 às 17:00"


def test_guess_observacoes_para_no_proximo_rotulo():
    obs = guess_observacoes(_TEXTO_RDO)
    assert len(obs) == 1
    assert "sem intercorrências" in obs[0]["descricao"]
    assert "Assinatura" not in obs[0]["descricao"]


def test_classify_equipamentos():
    rows = [
        ["Equipamento", "Empresa", "Quantidade"],
        ["Caminhão pipa", "ACME", "2"],
        ["Retroescavadeira", "ACME", "1"],
    ]
    target, items = classify_and_map_table(rows)
    assert target == "equipamentos"
    assert items == [
        {"nome": "Caminhão pipa", "empresa": "ACME", "quantidade": 2},
        {"nome": "Retroescavadeira", "empresa": "ACME", "quantidade": 1},
    ]


def test_classify_mao_de_obra_direta_e_indireta():
    direta = [["Função MOD", "Empresa", "Quantidade"], ["Pedreiro", "ACME", "5"]]
    indireta = [["Função MOI", "Empresa", "Quantidade"], ["Encarregado", "ACME", "1"]]
    assert classify_and_map_table(direta)[0] == "mao_de_obra_direta"
    assert classify_and_map_table(indireta)[0] == "mao_de_obra_indireta"


def test_classify_tabela_desconhecida_nao_inventa():
    rows = [["Coluna A", "Coluna B"], ["x", "y"]]
    assert classify_and_map_table(rows) == (None, [])


def test_split_into_blocks_corta_em_linhas_vazias():
    rows = [
        ["Equipamento", "Qtd"], ["Caminhão", "2"],
        ["", ""],
        ["Função", "Qtd"], ["Pedreiro", "5"],
    ]
    blocks = split_into_blocks(rows)
    assert len(blocks) == 2
    assert blocks[0][0] == ["Equipamento", "Qtd"]
    assert blocks[1][0] == ["Função", "Qtd"]


def test_export_rdo_workbook_mesmas_abas_da_skill():
    record = RdoRecord(
        numero_rdo="275", data_rdo="2026-04-10", local_obra="GERAL",
        horario_trabalho="07:00 às 17:00", contratante="GERDAU", contratada="EXXATA",
        source_file="4404-PL-RDO-0275.pdf", source_pages="1",
    )
    record.equipamentos.append(EquipamentoItem(nome="Caminhão pipa", empresa="ACME", quantidade=2))
    record.mao_de_obra_direta.append(MaoDeObraItem(funcao="Pedreiro", empresa="ACME", quantidade=5))

    wb = build_rdo_workbook([record])
    assert wb.sheetnames == [
        "Resumo RDOs", "Equipamentos", "Mão de Obra Direta", "Mão de Obra Indireta",
        "Atividades", "Observações",
    ]
    resumo = wb["Resumo RDOs"]
    header = [c.value for c in resumo[1]]
    row = [c.value for c in resumo[2]]
    data = dict(zip(header, row))
    assert data["numero_rdo"] == "275"
    assert data["total_mao_de_obra_direta"] == 5

    equip = wb["Equipamentos"]
    assert [c.value for c in equip[1]] == ["numero_rdo", "data_rdo", "nome", "empresa", "quantidade"]
    assert [c.value for c in equip[2]] == ["275", "2026-04-10", "Caminhão pipa", "ACME", 2]
