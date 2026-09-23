"""Compilador de Planilhas — interface web local (Streamlit)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from collections import Counter
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Compilador de Planilhas",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _confidence_color(conf: float) -> str:
    if conf >= 0.85:
        return "#C6EFCE"
    if conf >= 0.40:
        return "#FFEB9C"
    return "#FFC7CE"


def _status_icon(status: str) -> str:
    return {"ok": "✅", "review": "⚠️", "unidentified": "❌", "error": "❌", "skipped": "⏭️"}.get(status, "❓")


def _style_log_df(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    def row_color(row):
        status = row.get("status", "")
        color = "#C6EFCE" if status == "ok" else "#FFEB9C" if status == "review" else "#FFC7CE"
        return [f"background-color: {color}"] * len(row)
    return df.style.apply(row_color, axis=1)


def _load_catalog():
    from compilador.catalog.loader import load_catalog
    return load_catalog()


# ── Tab 1: Compilar .xlsx ─────────────────────────────────────────────────────

def tab_compilar():
    st.header("📊 Compilar arquivos .xlsx")
    st.markdown("Selecione uma pasta local. O sistema identificará cada arquivo automaticamente e consolidará tudo em um único `.xlsx` com rastreabilidade.")

    col1, col2 = st.columns([3, 1])
    with col1:
        input_dir = st.text_input(
            "Pasta de entrada",
            placeholder="/Users/usuario/planilhas/medicoes",
            help="Caminho absoluto da pasta com os arquivos .xlsx",
        )
    with col2:
        sample = st.number_input("Modo teste (N arquivos)", min_value=0, value=0, step=1,
                                  help="0 = processar todos. Use um número pequeno para testar antes do lote completo.")

    col3, col4, col5 = st.columns(3)
    with col3:
        recursive = st.checkbox("Busca recursiva em subpastas", value=True)
    with col4:
        dry_run = st.checkbox("Dry run (não escreve saída)", value=False)
    with col5:
        confidence_threshold = st.slider("Confiança mínima", 0.0, 1.0, 0.40, 0.05)

    iniciar = st.button("▶ Iniciar compilação", type="primary", use_container_width=True)

    if not iniciar:
        return

    if not input_dir or not Path(input_dir).is_dir():
        st.error("Pasta não encontrada. Verifique o caminho informado.")
        return

    from compilador.compiler.walker import compile_iter
    from compilador.compiler.assembler import assemble_output
    from compilador.common.models import CanonicalRow, FileResult

    # Discover file count first for accurate total
    pattern = "**/*.xlsx" if recursive else "*.xlsx"
    all_files = sorted(Path(input_dir).glob(pattern))
    n_sample = int(sample) if sample > 0 else None
    files_to_process = all_files[:n_sample] if n_sample else all_files
    total = len(files_to_process)

    if total == 0:
        st.warning("Nenhum arquivo .xlsx encontrado na pasta informada.")
        return

    st.markdown(f"**{total} arquivo(s) encontrado(s)**{' (modo teste)' if n_sample else ''}")

    progress_total = st.progress(0, text="📊 Progresso geral: 0 / " + str(total))
    current_file_text = st.empty()
    log_placeholder = st.empty()

    all_rows: list[CanonicalRow] = []
    all_results: list[FileResult] = []
    log_rows: list[dict] = []

    for event in compile_iter(
        input_dir,
        sample=n_sample,
        recursive=recursive,
        confidence_threshold=confidence_threshold,
    ):
        r = event.result
        if r:
            all_results.append(r)
            if hasattr(r, "_canonical_rows"):
                rows = r._canonical_rows  # type: ignore[attr-defined]
                for row in rows:
                    row.confidence = r.confidence
                    row.needs_review = r.needs_review
                all_rows.extend(rows)
            log_rows.append({
                "status": _status_icon(r.status),
                "arquivo": Path(r.path).name,
                "formato": r.format_id or "—",
                "confiança": f"{r.confidence:.2f}" if r.confidence > 0 else "—",
                "linhas": r.rows_extracted,
                "ocr": "✓" if r.ocr_used else "",
                "erro": r.error or "",
            })

        progress_total.progress(
            event.fraction,
            text=f"📊 Progresso geral: {event.current} / {event.total}",
        )
        current_file_text.caption(f"📄 Arquivo atual: **{event.filename}**")

        if log_rows:
            log_df = pd.DataFrame(log_rows)
            with log_placeholder.container():
                st.dataframe(log_df, use_container_width=True, hide_index=True)

    current_file_text.empty()
    progress_total.progress(1.0, text="✅ Concluído!")

    # Summary metrics
    st.divider()
    st.subheader("📋 Resumo do processamento")
    counts = Counter(r.status for r in all_results)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ Identificados", counts["ok"])
    m2.metric("⚠️ Revisão necessária", counts["review"])
    m3.metric("❌ Não identificados", counts["unidentified"])
    m4.metric("💥 Erros", counts["error"])

    # Format breakdown
    fmt_counts: Counter = Counter(r.format_id for r in all_results if r.format_id)
    if fmt_counts:
        st.markdown("**Por formato:**")
        fmt_df = pd.DataFrame(
            [{"Formato": k, "Arquivos": v} for k, v in fmt_counts.most_common()],
        )
        st.dataframe(fmt_df, use_container_width=True, hide_index=True)

    if not dry_run and all_results:
        output_bytes = assemble_output(all_rows, all_results)
        st.download_button(
            label="⬇ Baixar compilado.xlsx",
            data=output_bytes,
            file_name="compilado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

        # Download unidentified report
        unidentified = [r for r in all_results if r.status in ("unidentified", "error")]
        if unidentified:
            unid_lines = "\n".join(
                f"{Path(r.path).name}\t{r.status}\t{r.error or ''}" for r in unidentified
            )
            st.download_button(
                label="⬇ Baixar relatório de não identificados (.txt)",
                data=unid_lines,
                file_name="nao_identificados.txt",
                mime="text/plain",
            )
    elif dry_run:
        st.info("Dry run ativo — nenhum arquivo foi escrito.")


# ── Tab 2: Converter PDF ──────────────────────────────────────────────────────

def tab_converter_pdf():
    st.header("📄 Converter PDFs para .xlsx")
    st.markdown("Faça upload de um ou mais PDFs. O sistema identificará o formato e extrairá as tabelas, com fallback para OCR quando necessário.")

    uploaded_files = st.file_uploader(
        "Selecionar PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        help="Arraste e solte ou clique para selecionar",
    )

    col1, col2 = st.columns(2)
    with col1:
        force_ocr = st.checkbox("Forçar OCR (ignorar extração nativa)", value=False)
    with col2:
        ocr_lang = st.selectbox("Idioma OCR", ["por", "eng", "por+eng"], index=0)

    iniciar = st.button("▶ Iniciar conversão", type="primary", use_container_width=True,
                        disabled=not uploaded_files)

    if not iniciar or not uploaded_files:
        return

    # Check OCR availability
    ocr_available = True
    try:
        import pdf2image  # noqa: F401
        import pytesseract  # noqa: F401
    except ImportError:
        ocr_available = False
        if force_ocr:
            st.warning("⚠️ pdf2image/pytesseract não instalados — OCR indisponível. A conversão usará apenas pdfplumber e camelot.")

    from compilador.pdf_converter.pipeline import extract_tables
    from compilador.identifier.scorer import best_match
    from compilador.catalog.loader import load_catalog
    from compilador.compiler.extractor import extract
    from compilador.compiler.assembler import assemble_output
    from compilador.common.models import FileResult

    catalog = load_catalog()
    total = len(uploaded_files)
    progress = st.progress(0, text=f"📊 Progresso geral: 0 / {total}")
    current_text = st.empty()
    log_placeholder = st.empty()

    all_rows = []
    all_results: list[FileResult] = []
    log_rows: list[dict] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, uploaded in enumerate(uploaded_files, start=1):
            tmp_path = Path(tmpdir) / uploaded.name
            tmp_path.write_bytes(uploaded.read())

            result = FileResult(path=str(tmp_path))
            current_text.caption(f"📄 Processando: **{uploaded.name}**")

            try:
                tables, ocr_used = extract_tables(
                    tmp_path,
                    force_ocr=force_ocr and ocr_available,
                    ocr_lang=ocr_lang,
                )
                result.ocr_used = ocr_used
                if not tables:
                    result.error = "nenhuma tabela extraída"
                else:
                    match = best_match(tables[0], catalog)
                    if not match or match.confidence < 0.40:
                        result.confidence = match.confidence if match else 0.0
                    else:
                        fmt = catalog.get(match.format_id)
                        rows = extract(tables[0], fmt)
                        for row in rows:
                            row.confidence = match.confidence
                            row.ocr_used = ocr_used
                            row.needs_review = match.confidence < 0.85
                        all_rows.extend(rows)
                        result.format_id = match.format_id
                        result.confidence = match.confidence
                        result.needs_review = match.confidence < 0.85
                        result.rows_extracted = len(rows)
            except Exception as e:
                result.error = str(e)

            all_results.append(result)
            log_rows.append({
                "status": _status_icon(result.status),
                "arquivo": uploaded.name,
                "formato": result.format_id or "—",
                "confiança": f"{result.confidence:.2f}" if result.confidence > 0 else "—",
                "linhas": result.rows_extracted,
                "ocr": "✓" if result.ocr_used else "",
                "erro": result.error or "",
            })

            progress.progress(idx / total, text=f"📊 Progresso geral: {idx} / {total}")
            log_df = pd.DataFrame(log_rows)
            with log_placeholder.container():
                st.dataframe(log_df, use_container_width=True, hide_index=True)

    current_text.empty()
    progress.progress(1.0, text="✅ Concluído!")

    st.divider()
    st.subheader("📋 Resumo")
    counts = Counter(r.status for r in all_results)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ Convertidos", counts["ok"])
    m2.metric("⚠️ Revisão necessária", counts["review"])
    m3.metric("❌ Não identificados", counts["unidentified"])
    m4.metric("💥 Erros", counts["error"])

    if all_results:
        output_bytes = assemble_output(all_rows, all_results)
        st.download_button(
            label="⬇ Baixar resultado.xlsx",
            data=output_bytes,
            file_name="pdfs_convertidos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )


# ── Tab 3: Catálogo ───────────────────────────────────────────────────────────

def tab_catalogo():
    st.header("📚 Catálogo de Formatos")

    try:
        catalog = _load_catalog()
    except Exception as e:
        st.error(f"Erro ao carregar catálogo: {e}")
        return

    # Validation banner
    from compilador.catalog.manager import validate_catalog
    errors = validate_catalog()
    if errors:
        st.error("⚠️ Catálogo inválido:\n" + "\n".join(errors))
    else:
        st.success(f"✅ Catálogo válido — {len(catalog.formats)} formato(s) cadastrado(s)")

    st.divider()

    # List
    st.subheader("Formatos cadastrados")
    if catalog.formats:
        rows = [
            {
                "ID": f.format_id,
                "Nome": f.display_name,
                "Órgão": f.agency,
                "Tipo": f.document_type,
                "Versão": f.version,
            }
            for f in catalog.formats
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Catálogo vazio. Adicione formatos usando o painel abaixo.")

    st.divider()

    # Inspect
    st.subheader("Inspecionar formato")
    fmt_ids = [f.format_id for f in catalog.formats]
    if fmt_ids:
        selected = st.selectbox("Selecionar formato", fmt_ids)
        entry = catalog.get(selected)
        if entry:
            st.json(json.loads(entry.model_dump_json()))
    else:
        st.info("Nenhum formato disponível para inspecionar.")

    st.divider()

    # Add new format
    st.subheader("Adicionar novo formato")
    st.markdown(
        "Faça upload de um arquivo `.json` seguindo o [schema do catálogo]"
        "(veja um dos formatos acima como exemplo)."
    )
    new_fmt_file = st.file_uploader("Arquivo JSON do novo formato", type=["json"], key="new_fmt")
    if new_fmt_file and st.button("➕ Adicionar ao catálogo"):
        try:
            from compilador.catalog.loader import load_format_from_file, append_format
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as tmp:
                tmp.write(new_fmt_file.read())
                tmp_path = tmp.name
            entry = load_format_from_file(tmp_path)
            updated = append_format(entry)
            st.success(f"✅ Formato '{entry.format_id}' adicionado. Catálogo agora tem {len(updated.formats)} formatos.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao adicionar formato: {e}")

    st.divider()

    # Validate button
    st.subheader("Validar catálogo")
    if st.button("🔍 Validar agora"):
        errs = validate_catalog()
        if errs:
            for e in errs:
                st.error(e)
        else:
            st.success("Catálogo válido!")


# ── Tab 4: Configuração ───────────────────────────────────────────────────────

def _run_install_ui(tool: str, label: str) -> None:
    """Executa instalação de uma ferramenta com saída em tempo real na UI."""
    from compilador.setup_checker import install_tool, run_streaming

    cmd, manual = install_tool(tool)
    if cmd is None:
        st.warning(f"Instalação automática indisponível.\n\n{manual}")
        return

    st.caption(f"Executando: `{' '.join(cmd)}`  — pode demorar alguns minutos.")
    output_area = st.empty()
    lines: list[str] = []
    returncode = 1

    for line in run_streaming(cmd):
        if line.startswith("__done__:"):
            returncode = int(line.split(":")[1])
            break
        lines.append(line)
        output_area.code("\n".join(lines[-50:]), language=None)

    if returncode == 0:
        st.success(f"✅ {label} instalado com sucesso!")
        st.info("Clique em **🔄 Verificar novamente** para atualizar o status.")
    else:
        st.error(f"❌ Erro ao instalar {label}. Veja a saída acima.")
        if platform.system() == "Linux":
            st.warning("No Linux pode ser necessário digitar a senha de administrador no terminal onde o app está rodando.")


def tab_configuracao() -> None:
    import platform as _platform
    st.header("⚙️ Configuração do Sistema")
    st.markdown(
        "Verifique e instale as dependências necessárias para o funcionamento completo do sistema. "
        "A compilação de `.xlsx` funciona sem dependências adicionais. "
        "**Poppler** e **Tesseract** são necessários apenas para converter PDFs escaneados (OCR)."
    )

    from compilador.setup_checker import (
        check_all_python_packages,
        check_poppler,
        check_tesseract,
        check_brew,
    )

    # ── Pacotes Python ────────────────────────────────────────────────────────
    st.subheader("📦 Pacotes Python")
    python_pkgs = check_all_python_packages()
    all_python_ok = all(python_pkgs.values())

    pkg_df = pd.DataFrame(
        [{"Pacote": k, "Status": "✅ Instalado" if v else "❌ Faltando"} for k, v in python_pkgs.items()]
    )
    st.dataframe(pkg_df, use_container_width=True, hide_index=True)

    if not all_python_ok:
        missing_pkgs = [k for k, v in python_pkgs.items() if not v]
        st.warning(f"Faltando: **{', '.join(missing_pkgs)}**")
        if st.button("▶ Instalar pacotes Python faltantes", key="btn_pip"):
            _run_install_ui("python_packages", "pacotes Python")
    else:
        st.success("✅ Todos os pacotes Python estão instalados.")

    st.divider()

    # ── Dependências do sistema ───────────────────────────────────────────────
    st.subheader("🖥️ Dependências do Sistema")

    col1, col2 = st.columns(2)

    with col1:
        poppler_ok = check_poppler()
        st.markdown("**Poppler** — extração de tabelas em PDFs")
        if poppler_ok:
            st.success("✅ Instalado")
        else:
            st.error("❌ Não encontrado")
            if st.button("▶ Instalar Poppler", key="btn_poppler"):
                _run_install_ui("poppler", "Poppler")

    with col2:
        tesseract_ok = check_tesseract()
        st.markdown("**Tesseract OCR** — leitura de PDFs escaneados")
        if tesseract_ok:
            st.success("✅ Instalado")
        else:
            st.error("❌ Não encontrado")
            if st.button("▶ Instalar Tesseract OCR", key="btn_tesseract"):
                _run_install_ui("tesseract", "Tesseract OCR")

    # Instalar tudo de uma vez
    system_missing = (not poppler_ok) or (not tesseract_ok)
    if system_missing:
        st.divider()
        if st.button("▶ Instalar TODAS as dependências do sistema", type="primary", key="btn_all"):
            if not poppler_ok:
                st.markdown("**Instalando Poppler...**")
                _run_install_ui("poppler", "Poppler")
            if not tesseract_ok:
                st.markdown("**Instalando Tesseract OCR...**")
                _run_install_ui("tesseract", "Tesseract OCR")

    # macOS: alertar se brew não está instalado
    if _platform.system() == "Darwin" and not check_brew():
        st.divider()
        st.error(
            "**Homebrew não encontrado.**  \n"
            "O Homebrew é necessário para instalar Poppler e Tesseract no macOS.  \n"
            "Instale em: https://brew.sh — depois volte aqui e clique nos botões acima."
        )

    st.divider()

    # ── Verificar novamente ───────────────────────────────────────────────────
    st.subheader("🔄 Atualizar status")
    st.caption("Clique abaixo após uma instalação para verificar o novo status.")
    if st.button("🔄 Verificar novamente", key="btn_recheck"):
        st.rerun()

    # ── Informações do sistema ────────────────────────────────────────────────
    with st.expander("ℹ️ Informações do sistema"):
        import sys as _sys
        st.markdown(f"""
| Item | Valor |
|------|-------|
| Sistema operacional | `{_platform.system()} {_platform.release()}` |
| Python | `{_sys.version}` |
| Homebrew | `{'✅ Encontrado' if check_brew() else '❌ Não encontrado'}` |
| Poppler | `{'✅ Encontrado' if check_poppler() else '❌ Não encontrado'}` |
| Tesseract | `{'✅ Encontrado' if check_tesseract() else '❌ Não encontrado'}` |
        """)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import platform

    st.title("📊 Compilador de Planilhas")
    st.caption("Administração contratual de obras de infraestrutura civil")

    # Banner de aviso se dependências opcionais estiverem faltando
    from compilador.setup_checker import get_missing_system_deps
    missing = get_missing_system_deps()
    if missing:
        names = " e ".join(missing)
        st.warning(
            f"⚠️ **{names}** não {'estão' if len(missing) > 1 else 'está'} instalado{'s' if len(missing) > 1 else ''}. "
            f"A compilação de `.xlsx` funciona normalmente. "
            f"Para converter PDFs escaneados, acesse a aba **⚙️ Configuração**.",
        )

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Compilar .xlsx", "📄 Converter PDF", "📚 Catálogo", "⚙️ Configuração"]
    )

    with tab1:
        tab_compilar()
    with tab2:
        tab_converter_pdf()
    with tab3:
        tab_catalogo()
    with tab4:
        tab_configuracao()


main()
