"""Modelos de dados do RDO (Relatório Diário de Obra).

Espelham o contrato usado pela skill `exxata-rdo-extractor`
(ver references/contracts.md dessa skill): mesmos campos, mesmos nomes,
mesmas listas. A diferença é só o modo de preenchimento — aqui é feito por
heurística local + revisão manual na tela, em vez de uma IA hospedeira.
"""
from dataclasses import dataclass, field


@dataclass
class ClimaInfo:
    manha: str = ""
    tarde: str = ""
    noite: str = ""
    pluviometria_manha: float = 0.0
    pluviometria_tarde: float = 0.0
    pluviometria_noite: float = 0.0


@dataclass
class EquipamentoItem:
    nome: str = ""
    empresa: str = ""
    quantidade: int = 0


@dataclass
class MaoDeObraItem:
    funcao: str = ""
    empresa: str = ""
    quantidade: int = 0


@dataclass
class AtividadeItem:
    secao: str = ""
    item: str = ""
    descricao: str = ""
    empresa: str = ""


@dataclass
class ObservacaoItem:
    autor: str = ""
    descricao: str = ""
    empresa: str = ""


@dataclass
class RdoRecord:
    numero_rdo: str = ""
    data_rdo: str = ""
    local_obra: str = ""
    horario_trabalho: str = ""
    contratante: str = ""
    contratada: str = ""
    clima: ClimaInfo = field(default_factory=ClimaInfo)
    equipamentos: list[EquipamentoItem] = field(default_factory=list)
    mao_de_obra_direta: list[MaoDeObraItem] = field(default_factory=list)
    mao_de_obra_indireta: list[MaoDeObraItem] = field(default_factory=list)
    atividades: list[AtividadeItem] = field(default_factory=list)
    observacoes: list[ObservacaoItem] = field(default_factory=list)
    # Rastreabilidade (não faz parte do contrato original da skill, mas segue o
    # padrão do restante do compilador: toda saída deve indicar a origem).
    source_file: str = ""
    source_pages: str = ""
