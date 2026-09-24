"""Pré-preenchimento heurístico do RDO a partir de texto e tabelas já extraídos.

Isto NÃO é o mesmo mecanismo da skill `exxata-rdo-extractor` (lá quem lê e
estrutura o texto é a IA hospedeira). Aqui é busca por rótulo conhecido +
classificação de tabelas por palavra-chave de cabeçalho — cobre bem RDOs com
rótulos e tabelas "limpos", e propositalmente deixa em branco o que não
reconhecer com segurança, para o usuário completar na tela de revisão em vez
de arriscar inventar dado (mesma regra de ouro da skill: nunca inventar).
"""
import re
from ..identifier.normalizer import normalize
from .models import RdoRecord, ClimaInfo

_FIELD_PATTERNS: dict[str, list[str]] = {
    "numero_rdo": [
        # Símbolo de ordinal (º/°) obrigatório, não "o" solto — senão "no RDO"
        # (dentro do RDO) é lido como "Nº RDO" (número do RDO).
        r"rdo\.?\s*n[º°]\.?\s*[:\-]?\s*(\S+)",
        r"\bn[º°]\.?\s*(?:do\s*)?rdo\s*[:\-]?\s*(\S+)",
        r"relat[óo]rio\s*di[áa]rio\s*de\s*obra\s*n[º°]\.?\s*[:\-]?\s*(\S+)",
    ],
    "data_rdo": [
        r"data\s*(?:do\s*rdo)?\s*[:\-]?\s*(\d{2}[/\-.]\d{2}[/\-.]\d{4})",
    ],
    "local_obra": [
        # ':' obrigatório — "obra" e "empreendimento" são palavras comuns em texto
        # livre e só contam como rótulo quando seguidas de dois-pontos.
        r"(?:local\s*da\s*obra|obra|empreendimento)\s*[:\-]\s*([^\n|]{1,80}?)(?=\s{2,}|\n|\||$)",
    ],
    "horario_trabalho": [
        r"hor[áa]rio\s*de\s*trabalho\s*[:\-]\s*([^\n|]{1,40}?)(?=\s{2,}|\n|\||$)",
        r"turno\s*[:\-]\s*([^\n|]{1,40}?)(?=\s{2,}|\n|\||$)",
    ],
    "contratante": [
        r"contratante\s*[:\-]\s*([^\n|]{1,80}?)(?=\s{2,}|\n|\||$)",
        r"cliente\s*[:\-]\s*([^\n|]{1,80}?)(?=\s{2,}|\n|\||$)",
    ],
    "contratada": [
        r"contratada\s*[:\-]\s*([^\n|]{1,80}?)(?=\s{2,}|\n|\||$)",
        r"empresa\s*execut(?:ora|antes)?\s*[:\-]\s*([^\n|]{1,80}?)(?=\s{2,}|\n|\||$)",
    ],
}

_HORA_INICIO_RE = r"hor[áa]rio\s*(?:de\s*)?in[íi]cio\s*[:\-]?\s*(\d{1,2}[:h]\d{2})"
_HORA_FIM_RE = r"hor[áa]rio\s*(?:de\s*)?t[ée]rmino\s*[:\-]?\s*(\d{1,2}[:h]\d{2})"
_DATE_RE = re.compile(r"^(\d{2})[/\-.](\d{2})[/\-.](\d{4})$")
_CLIMA_PERIODOS = {"manha": ["manha", "manhã"], "tarde": ["tarde"], "noite": ["noite"]}
_CLIMA_PALAVRAS = ["bom", "nublado", "chuvoso", "chuva", "sol", "ensolarado", "nevoeiro", "garoa", "encoberto"]

# Rótulos que às vezes aparecem repetidos como cabeçalho de outra seção do
# documento (ex.: "01 - CONTRATADA: DESCRIÇÃO DAS ATIVIDADES") — se o valor
# capturado for só isso, não é o nome de uma empresa/local, é outro título.
_OUTRO_ROTULO_RE = re.compile(
    r"\b(data|contratante|contratada|hor[áa]rio|cliente|local|obra|turno|empreendimento|rdo)\b",
    re.IGNORECASE,
)
_SECTION_HEADING_WORDS = {
    "descricao", "descricao das atividades", "atividades", "efetivo", "assinatura",
    "assinaturas", "observacoes", "observacao", "geral", "equipamentos", "mao de obra",
}


def _clean_captured(value: str) -> str:
    """Corta o valor capturado no ponto em que ele parece ter engolido o próximo
    rótulo do documento (comum quando o layout original é multi-coluna e a
    extração de texto lineariza colunas diferentes na mesma linha)."""
    m = _OUTRO_ROTULO_RE.search(value)
    if m and m.start() > 0:
        value = value[: m.start()]
    return value.strip(" .:-\t")


def _looks_like_heading(value: str) -> bool:
    norm = normalize(value)
    return norm in _SECTION_HEADING_WORDS or all(w in _SECTION_HEADING_WORDS for w in norm.split())


_TEXT_FIELDS = {"local_obra", "contratante", "contratada"}  # devem conter letras, não só números


def _first_match(patterns: list[str], text: str, reject_numeric: bool = False) -> str:
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            value = _clean_captured(m.group(1))
            if not value or _looks_like_heading(value):
                continue
            if reject_numeric and re.fullmatch(r"[\d./\-]+", value):
                continue
            return value
    return ""


def _to_iso_date(value: str) -> str:
    m = _DATE_RE.match(value.strip())
    if not m:
        return ""
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"


def guess_header_fields(text: str) -> dict[str, str]:
    """Tenta localizar os campos-base do RDO por rótulo conhecido no texto."""
    fields = {
        name: _first_match(patterns, text, reject_numeric=name in _TEXT_FIELDS)
        for name, patterns in _FIELD_PATTERNS.items()
    }
    if not fields["horario_trabalho"]:
        inicio = _first_match([_HORA_INICIO_RE], text)
        fim = _first_match([_HORA_FIM_RE], text)
        if inicio or fim:
            fields["horario_trabalho"] = " às ".join(p for p in (inicio, fim) if p)
    if fields["data_rdo"]:
        fields["data_rdo"] = _to_iso_date(fields["data_rdo"]) or fields["data_rdo"]
    return fields


def guess_clima(text: str) -> ClimaInfo:
    """Só preenche um período quando encontra 'Manhã: <condição conhecida>' (ou
    similar) explicitamente no texto — não tenta adivinhar em grades de checkbox."""
    clima = ClimaInfo()
    for attr, labels in _CLIMA_PERIODOS.items():
        for label in labels:
            m = re.search(rf"\b{label}\b\s*[:\-]\s*([a-zà-úA-ZÀ-Ú ]{{1,20}})", text, re.IGNORECASE)
            if m:
                candidate = normalize(m.group(1))
                for palavra in _CLIMA_PALAVRAS:
                    if palavra in candidate:
                        setattr(clima, attr, m.group(1).strip().title())
                        break
                if getattr(clima, attr):
                    break
    return clima


def guess_observacoes(text: str) -> list[dict]:
    m = re.search(r"observa(?:c|ç)(?:ao|ão|oes|ões)\s*[:\-]?\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    trecho = m.group(1).strip()
    trecho = re.split(
        r"\n\s*(assinatura|respons[áa]vel\s+t[ée]cnico|encarregado)\b", trecho, maxsplit=1, flags=re.IGNORECASE
    )[0].strip()
    if not trecho:
        return []
    return [{"autor": "", "descricao": trecho[:2000], "empresa": ""}]


def _as_int(value) -> int:
    try:
        return int(float(str(value).replace(",", ".").strip()))
    except (ValueError, TypeError):
        return 0


def classify_and_map_table(rows: list[list[str]]) -> tuple[str | None, list[dict]]:
    """Identifica a que lista do RDO um bloco de tabela pertence (equipamentos,
    mão de obra direta/indireta ou atividades) e mapeia suas colunas por palavra-chave.
    Retorna (None, []) quando não reconhece o cabeçalho com confiança."""
    if not rows or not rows[0]:
        return None, []
    header = [normalize(c) for c in rows[0]]
    body = rows[1:]

    def col_index(*keywords: str) -> int | None:
        for idx, cell in enumerate(header):
            if any(k in cell for k in keywords):
                return idx
        return None

    header_joined = " ".join(header)
    if any(("equipamento" in c or "veiculo" in c or "maquina" in c) for c in header):
        target = "equipamentos"
        keys = ("nome", "empresa", "quantidade")
        idxs = (
            col_index("equipamento", "veiculo", "maquina", "descricao", "nome"),
            col_index("empresa", "fornecedor", "subcontratada"),
            col_index("quantidade", "qtd", "qde"),
        )
    elif any(
        ("funcao" in c or "cargo" in c or "efetivo" in c or "mao de obra" in c or "mao-de-obra" in c) for c in header
    ):
        is_indireta = bool(re.search(r"\b(indireta|moi)\b", header_joined))
        target = "mao_de_obra_indireta" if is_indireta else "mao_de_obra_direta"
        keys = ("funcao", "empresa", "quantidade")
        idxs = (
            col_index("funcao", "cargo", "categoria", "descricao"),
            col_index("empresa", "subcontratada", "fornecedor"),
            col_index("quantidade", "qtd", "efetivo", "qde"),
        )
    elif any(("atividade" in c or "servico" in c) for c in header):
        target = "atividades"
        keys = ("secao", "item", "descricao", "empresa")
        idxs = (
            col_index("secao", "etapa", "frente"),
            col_index("item", "codigo"),
            col_index("descricao", "atividade", "servico"),
            col_index("empresa", "equipe", "responsavel"),
        )
    else:
        return None, []

    items = []
    for row in body:
        if not any(str(c).strip() for c in row if c):
            continue
        item: dict = {}
        for key, idx in zip(keys, idxs):
            value = row[idx].strip() if idx is not None and idx < len(row) and row[idx] else ""
            item[key] = _as_int(value) if key == "quantidade" else value
        if any(str(v).strip() for v in item.values()):
            items.append(item)
    return target, items


def prefill_rdo(group, options: dict[str, bool]) -> RdoRecord:
    """Monta um RdoRecord com o melhor palpite a partir do texto/tabelas do grupo."""
    record = RdoRecord(
        source_file=group.source_file,
        source_pages="-".join(map(str, group.pages)) if group.pages else "",
        **guess_header_fields(group.text),
    )
    if options.get("clima"):
        record.clima = guess_clima(group.text)
    if options.get("equipamentos") or options.get("maoDeObra") or options.get("atividades"):
        for block in group.tables:
            target, items = classify_and_map_table(block)
            if target == "equipamentos" and options.get("equipamentos"):
                record.equipamentos.extend(items)
            elif target in ("mao_de_obra_direta", "mao_de_obra_indireta") and options.get("maoDeObra"):
                getattr(record, target).extend(items)
            elif target == "atividades" and options.get("atividades"):
                record.atividades.extend(items)
    if options.get("atividades"):
        record.observacoes = guess_observacoes(group.text)
    return record
