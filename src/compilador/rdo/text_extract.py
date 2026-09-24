"""Leitura de páginas/tabelas de RDOs a partir de PDF, imagem ou .xlsx, e
agrupamento de páginas em relatórios (um RDO pode ocupar 1 ou várias páginas)."""
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger


@dataclass
class RdoGroup:
    source_file: str
    pages: list[int]  # 1-based; vazio para .xlsx (não paginado)
    text: str
    # Blocos de tabela já isolados (cabeçalho + linhas), prontos para classificação.
    tables: list[list[list[str]]] = field(default_factory=list)


def split_into_blocks(rows: list[list[str]]) -> list[list[list[str]]]:
    """Separa uma matriz de células em blocos de tabela, cortando em linhas vazias.

    Uma aba de planilha ou uma tabela extraída de PDF costuma conter mais de uma
    tabela lógica (equipamentos, mão de obra, atividades) empilhadas com uma linha
    em branco entre elas; isso as separa para que cada uma seja classificada por si.
    """
    blocks: list[list[list[str]]] = []
    current: list[list[str]] = []
    for row in rows:
        cells = [("" if c is None else str(c)) for c in row]
        if any(c.strip() for c in cells):
            current.append(cells)
        else:
            if len(current) >= 2:
                blocks.append(current)
            current = []
    if len(current) >= 2:
        blocks.append(current)
    return blocks


def _extract_pdf_pages(pdf_path: Path, ocr_lang: str, ocr_dpi: int) -> tuple[list[str], list[list[list[list[str]]]]]:
    import pdfplumber

    texts: list[str] = []
    tables_per_page: list[list[list[list[str]]]] = []
    scanned_pages: list[int] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").strip()
            if len(text) < 20:
                scanned_pages.append(i)
            texts.append(text)
            blocks = []
            for t in page.extract_tables() or []:
                blocks.extend(split_into_blocks(t))
            tables_per_page.append(blocks)

    if scanned_pages:
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            logger.warning(
                f"OCR indisponível para {len(scanned_pages)} página(s) sem texto de {pdf_path.name}"
            )
            return texts, tables_per_page
        try:
            images = convert_from_path(str(pdf_path), dpi=ocr_dpi)
        except Exception as e:
            logger.warning(f"Falha ao rasterizar {pdf_path.name} para OCR: {e}")
            return texts, tables_per_page
        for i in scanned_pages:
            if i < len(images):
                try:
                    texts[i] = pytesseract.image_to_string(images[i], lang=ocr_lang).strip()
                except Exception as e:
                    logger.warning(f"OCR falhou na página {i + 1} de {pdf_path.name}: {e}")
    return texts, tables_per_page


def _extract_image(image_path: Path, ocr_lang: str) -> str:
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning("pytesseract/Pillow não instalados — OCR indisponível para imagens")
        return ""
    try:
        return pytesseract.image_to_string(Image.open(image_path), lang=ocr_lang).strip()
    except Exception as e:
        logger.warning(f"OCR falhou em {image_path.name}: {e}")
        return ""


def build_groups_from_pdf(
    path: str | Path, mode: str = "merge", ocr_lang: str = "por", ocr_dpi: int = 300
) -> list[RdoGroup]:
    """mode: 'merge' (o arquivo inteiro é um RDO) ou 'split' (cada página é um RDO)."""
    path = Path(path)
    texts, tables_per_page = _extract_pdf_pages(path, ocr_lang, ocr_dpi)
    n = len(texts)
    if n == 0:
        return []
    page_groups = [[i] for i in range(n)] if mode == "split" else [list(range(n))]
    groups = []
    for idxs in page_groups:
        text = "\n\n".join(texts[i] for i in idxs)
        tables = [t for i in idxs for t in tables_per_page[i]]
        groups.append(RdoGroup(source_file=path.name, pages=[i + 1 for i in idxs], text=text, tables=tables))
    return groups


def build_groups_from_image(path: str | Path, ocr_lang: str = "por") -> list[RdoGroup]:
    path = Path(path)
    text = _extract_image(path, ocr_lang)
    return [RdoGroup(source_file=path.name, pages=[1], text=text, tables=[])]


def build_groups_from_xlsx(path: str | Path, mode: str = "merge") -> list[RdoGroup]:
    """mode: 'merge' (o arquivo inteiro é um RDO) ou 'split' (cada aba é um RDO)."""
    from ..compiler.reader import read_xlsx

    path = Path(path)
    tables = read_xlsx(path)
    if not tables:
        return []
    if mode == "split":
        sheet_groups = [[t] for t in tables]
    else:
        sheet_groups = [tables]
    groups = []
    for sheets in sheet_groups:
        text = "\n".join(" | ".join(row) for t in sheets for row in t.rows)
        blocks = [b for t in sheets for b in split_into_blocks(t.rows)]
        label = "+".join(t.sheet_name for t in sheets)
        groups.append(RdoGroup(source_file=f"{path.name} ({label})", pages=[], text=text, tables=blocks))
    return groups
