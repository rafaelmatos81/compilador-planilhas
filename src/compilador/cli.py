from pathlib import Path
from typing import Optional
from collections import Counter
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="compilador",
    help="Compilador de planilhas e conversor de PDFs para administração contratual.",
    add_completion=False,
)
catalog_app = typer.Typer(help="Gerenciamento do catálogo de formatos.")
app.add_typer(catalog_app, name="catalog")
console = Console()


@app.command()
def compile(
    input_dir: Path = typer.Argument(..., help="Pasta com arquivos .xlsx"),
    output: Path = typer.Argument(..., help="Arquivo .xlsx de saída"),
    sample: Optional[int] = typer.Option(None, help="Processar apenas N arquivos (modo teste)"),
    recursive: bool = typer.Option(True, help="Busca recursiva"),
    dry_run: bool = typer.Option(False, help="Apenas identifica, sem escrever saída"),
    confidence_threshold: float = typer.Option(0.60, help="Confiança mínima para extração"),
) -> None:
    """Compilar arquivos .xlsx em um único arquivo consolidado."""
    from .compiler.walker import compile_iter
    from .compiler.assembler import assemble_output
    from .common.models import CanonicalRow, FileResult

    all_rows: list[CanonicalRow] = []
    all_results: list[FileResult] = []

    with console.status("[bold green]Processando arquivos..."):
        for event in compile_iter(
            input_dir,
            sample=sample,
            recursive=recursive,
            confidence_threshold=confidence_threshold,
        ):
            r = event.result
            if r:
                all_results.append(r)
                all_rows.extend(r.rows)
            console.log(f"{r.icon if r else '?'}  {event.filename}  [{event.current}/{event.total}]")

    if not dry_run:
        assemble_output(all_rows, all_results, output)
        console.print(f"\n[bold green]Salvo em:[/] {output}  ({len(all_rows)} linhas)")
    else:
        console.print(f"\n[bold yellow]Dry run — nada escrito. {len(all_results)} arquivos analisados.[/]")

    _print_summary(all_results)


@app.command("convert-pdf")
def convert_pdf(
    input_path: Path = typer.Argument(..., help="PDF ou pasta de PDFs"),
    output: Optional[Path] = typer.Option(None, help="Arquivo .xlsx de saída"),
    force_ocr: bool = typer.Option(False, help="Forçar OCR"),
    sample: Optional[int] = typer.Option(None),
) -> None:
    """Converter PDF(s) para .xlsx usando o catálogo de formatos."""
    from .pdf_converter.pipeline import extract_tables
    from .identifier.scorer import best_match_among
    from .catalog.loader import load_catalog
    from .catalog.schema import load_schema
    from .compiler.extractor import extract, extract_auto
    from .compiler.assembler import assemble_output
    from .common.models import FileResult
    from .config import settings

    catalog = load_catalog()
    schema = load_schema()
    pdfs = sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]
    if sample:
        pdfs = pdfs[:sample]

    all_rows = []
    all_results = []
    for pdf in pdfs:
        result = FileResult(path=str(pdf))
        try:
            tables, ocr_used = extract_tables(pdf, force_ocr=force_ocr)
            result.ocr_used = ocr_used
            if not tables:
                result.error = "no tables extracted"
                all_results.append(result)
                continue
            best_score, best_table = best_match_among(tables, catalog)
            if best_score is None or best_score.confidence < settings.confidence_medium:
                # Sem modelo cadastrado (ou confiança insuficiente): extrai mesmo assim
                # com mapeamento automático. Cadastrar um modelo é só um diferencial.
                result.confidence = best_score.confidence if best_score else 0.0
                layout_table = best_table or max(tables, key=len)
                rows = extract_auto(layout_table, schema)
                for row in rows:
                    row.ocr_used = ocr_used
                all_rows.extend(rows)
                result.rows_extracted = len(rows)
                all_results.append(result)
                continue
            fmt = catalog.get(best_score.format_id)
            rows = extract(best_table, fmt)
            for row in rows:
                row.confidence = best_score.confidence
                row.ocr_used = ocr_used
                row.needs_review = best_score.confidence < settings.confidence_high
            all_rows.extend(rows)
            result.format_id = best_score.format_id
            result.confidence = best_score.confidence
            result.needs_review = best_score.confidence < settings.confidence_high
            result.rows_extracted = len(rows)
        except Exception as e:
            result.error = str(e)
        all_results.append(result)

    out_path = output or (input_path.parent / (input_path.stem + "_converted.xlsx"))
    assemble_output(all_rows, all_results, out_path)
    console.print(f"[bold green]Convertido:[/] {out_path}")
    _print_summary(all_results)


@app.command()
def identify(
    file: Path = typer.Argument(..., help="Arquivo .xlsx para identificar"),
    top: int = typer.Option(3, help="Mostrar top N formatos"),
) -> None:
    """Identificar o formato de um .xlsx e mostrar ranking de confiança."""
    from .compiler.reader import read_xlsx
    from .identifier.scorer import score_all
    from .catalog.loader import load_catalog

    catalog = load_catalog()
    tables = read_xlsx(file)
    if not tables:
        console.print("[red]Nenhuma aba legível encontrada.[/]")
        raise typer.Exit(1)

    matches = score_all(tables[0], catalog)[:top]
    t = Table(title=f"Identificação: {file.name}")
    t.add_column("Formato", style="cyan")
    t.add_column("Confiança", justify="right")
    t.add_column("Âncoras encontradas")
    for m in matches:
        color = "green" if m.confidence >= 0.85 else "yellow" if m.confidence >= 0.40 else "red"
        t.add_row(
            m.format_id,
            f"[{color}]{m.confidence:.2f}[/{color}]",
            ", ".join(m.matched_anchors[:5]),
        )
    console.print(t)


@catalog_app.command("list")
def catalog_list(
    agency: Optional[str] = typer.Option(None),
    doc_type: Optional[str] = typer.Option(None, "--type"),
    verbose: bool = typer.Option(False),
) -> None:
    """Listar formatos no catálogo."""
    from .catalog.manager import list_formats
    fmts = list_formats()
    if agency:
        fmts = [f for f in fmts if f.agency.lower() == agency.lower()]
    if doc_type:
        fmts = [f for f in fmts if f.document_type.lower() == doc_type.lower()]
    t = Table(title="Catálogo de Formatos")
    t.add_column("ID", style="cyan")
    t.add_column("Nome")
    t.add_column("Órgão")
    t.add_column("Tipo")
    for f in fmts:
        t.add_row(f.format_id, f.display_name, f.agency, f.document_type)
    console.print(t)


@catalog_app.command("inspect")
def catalog_inspect(format_id: str = typer.Argument(...)) -> None:
    """Inspecionar uma entrada do catálogo."""
    from .catalog.manager import inspect_format
    fmt = inspect_format(format_id)
    console.print_json(fmt.model_dump_json(indent=2))


@catalog_app.command("add")
def catalog_add(format_file: Path = typer.Argument(..., help="JSON de nova entrada")) -> None:
    """Adicionar formato ao catálogo."""
    from .catalog.manager import add_format_from_file
    catalog = add_format_from_file(format_file)
    console.print(f"[green]Adicionado. Catálogo agora tem {len(catalog.formats)} formatos.[/]")


@catalog_app.command("validate")
def catalog_validate() -> None:
    """Validar catálogo completo."""
    from .catalog.manager import validate_catalog
    errors = validate_catalog()
    if errors:
        for e in errors:
            console.print(f"[red]ERRO:[/] {e}")
        raise typer.Exit(1)
    console.print("[green]Catálogo válido.[/]")


@catalog_app.command("test")
def catalog_test(
    format_id: str = typer.Argument(...),
    file: Path = typer.Argument(...),
) -> None:
    """Testar scoring de um formato contra um arquivo."""
    from .compiler.reader import read_xlsx
    from .identifier.scorer import score_all
    from .catalog.loader import load_catalog
    catalog = load_catalog()
    tables = read_xlsx(file)
    if not tables:
        console.print("[red]Sem abas legíveis.[/]")
        raise typer.Exit(1)
    matches = score_all(tables[0], catalog)
    t = Table(title=f"Teste: {format_id} vs {file.name}")
    t.add_column("Formato")
    t.add_column("Confiança", justify="right")
    t.add_column("★")
    for m in matches:
        highlight = "★" if m.format_id == format_id else ""
        color = "green" if m.confidence >= 0.85 else "yellow" if m.confidence >= 0.40 else "red"
        t.add_row(m.format_id, f"[{color}]{m.confidence:.2f}[/{color}]", highlight)
    console.print(t)


def _print_summary(results: list) -> None:
    counts = Counter(r.status for r in results)
    console.print(
        f"\n[bold]Resumo:[/] ✅ {counts['ok']}  ⚠️  {counts['review']}  "
        f"❌ {counts['unidentified']}  💥 {counts['error']}"
    )


if __name__ == "__main__":
    app()
