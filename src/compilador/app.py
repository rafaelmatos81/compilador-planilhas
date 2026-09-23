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


# ── Aprendizado de modelo (usado na aba "Novo modelo" e na compilação) ────────

@st.cache_data(show_spinner=False)
def _read_tables(path: str, mtime: float):
    from compilador.compiler.reader import read_xlsx
    return read_xlsx(Path(path))


def _save_upload(uploaded) -> Path:
    folder = Path(st.session_state.setdefault("_upload_dir", tempfile.mkdtemp(prefix="compilador_")))
    path = folder / uploaded.name
    data = uploaded.getvalue()
    if not path.exists() or path.stat().st_size != len(data):
        path.write_bytes(data)
    return path


def _learn_ui(path: Path, key: str, sheet_hint: str = "", check_existing: bool = False):
    """Interface para ensinar um modelo a partir de uma planilha de exemplo.

    Retorna o FormatEntry salvo (na execução em que o usuário clica em salvar) ou None.
    """
    from compilador import learner
    from compilador.catalog.loader import append_format, load_catalog
    from compilador.catalog.schema import add_field, load_schema
    from compilador.common.exceptions import CatalogError
    from compilador.compiler.extractor import extract
    from compilador.config import settings

    try:
        tables = _read_tables(str(path), path.stat().st_mtime)
    except Exception as e:
        st.error(f"Não foi possível ler {path.name}: {e}")
        return None
    if not tables:
        st.warning(f"{path.name} não tem nenhuma aba com conteúdo.")
        return None

    schema = load_schema()
    catalog = load_catalog()

    names = [t.sheet_name for t in tables]
    table = tables[0]
    if len(tables) > 1:
        default = names.index(sheet_hint) if sheet_hint in names else 0
        table = tables[names.index(st.selectbox("Aba da planilha", names, index=default, key=f"{key}_sheet"))]
    sheet = table.sheet_name

    if check_existing:
        from compilador.identifier.scorer import best_match
        match = best_match(table, catalog)
        if match and match.confidence >= settings.confidence_medium:
            st.info(
                f"Esta planilha já é reconhecida pelo modelo **{match.format_id}** "
                f"(confiança {match.confidence:.2f}). Cadastre outro modelo só se quiser um mapeamento diferente."
            )

    st.markdown("**1. Onde estão os títulos das colunas?**")
    detected = learner.detect_header_row(table)
    header_row = st.number_input(
        "Linha do cabeçalho", min_value=1, max_value=len(table.rows), value=detected + 1,
        key=f"{key}_hdr_{sheet}", help="Detectada automaticamente; ajuste se estiver errada.",
    )
    header_idx = int(header_row) - 1
    preview = pd.DataFrame(table.rows[: max(15, header_idx + 6)])
    preview.index = range(1, len(preview) + 1)
    st.dataframe(preview, use_container_width=True)

    infos = learner.describe_columns(table, header_idx, schema)
    if not infos:
        st.error("A linha escolhida não tem títulos de coluna.")
        return None

    st.markdown("**2. A qual coluna padrão corresponde cada coluna da planilha?**")
    options = [None, *schema.names()]
    h1, h2, h3 = st.columns([2, 3, 3])
    h1.caption("Coluna na planilha")
    h2.caption("Exemplos")
    h3.caption("Coluna padrão")
    mapping: dict[int, str] = {}
    for info in infos:
        c1, c2, c3 = st.columns([2, 3, 3])
        c1.markdown(f"**{info.header}**")
        c2.caption(" · ".join(info.samples) or "(vazia)")
        choice = c3.selectbox(
            "Coluna padrão", options,
            index=options.index(info.suggestion) if info.suggestion in options else 0,
            format_func=lambda n: "— ignorar —" if n is None else schema.label(n),
            key=f"{key}_map_{sheet}_{header_row}_{info.index}",
            label_visibility="collapsed",
        )
        if choice:
            mapping[info.index] = choice

    with st.expander("➕ Preciso de uma coluna padrão que não existe"):
        n1, n2, n3 = st.columns([3, 2, 1])
        new_label = n1.text_input("Nome da nova coluna", key=f"{key}_newlabel")
        type_label = n2.selectbox("Tipo", ["Texto", "Número", "Data"], key=f"{key}_newtype")
        n3.write("")
        if n3.button("Criar", key=f"{key}_newbtn"):
            try:
                add_field(new_label, {"Texto": "text", "Número": "number", "Data": "date"}[type_label])
                st.rerun()
            except CatalogError as e:
                st.error(str(e))
        st.caption("Depois de criar, escolha a nova coluna na lista de uma das colunas acima.")

    st.markdown("**3. Nome do modelo**")
    n1, n2, n3 = st.columns(3)
    name = n1.text_input("Nome do modelo *", value=path.stem, key=f"{key}_name")
    agency = n2.text_input("Órgão / fonte (opcional)", key=f"{key}_agency")
    doc_type = n3.text_input("Tipo de documento (opcional)", key=f"{key}_doctype")
    skip_text = st.text_input(
        "Ignorar linhas cuja primeira célula contenha", value=", ".join(learner.DEFAULT_SKIP_ROWS),
        key=f"{key}_skip", help="Separe por vírgula. Útil para linhas de total e subtotal.",
    )

    values = list(mapping.values())
    if len(values) != len(set(values)):
        st.error("Uma mesma coluna padrão foi escolhida para mais de uma coluna da planilha.")
        return None

    entry = None
    if mapping and name.strip():
        entry = learner.build_format(
            table, header_idx, mapping, name=name, agency=agency, document_type=doc_type,
            skip_rows=[s.strip() for s in skip_text.split(",") if s.strip()],
            description=f"Aprendido de {path.name}", existing_ids=catalog.ids(),
        )
        extracted = extract(table, entry)
        st.markdown(f"**Prévia:** {len(extracted)} linha(s) seriam extraídas desta planilha.")
        if extracted:
            st.dataframe(
                pd.DataFrame([r.data for r in extracted[:10]]).rename(columns=schema.label),
                use_container_width=True, hide_index=True,
            )
        else:
            st.warning("Nenhuma linha de dados foi extraída. Confira a linha do cabeçalho e o mapeamento.")

    if st.button("💾 Salvar modelo", type="primary", key=f"{key}_save", disabled=entry is None):
        append_format(entry)
        return entry
    return None


# ── Tab 1: Compilar .xlsx ─────────────────────────────────────────────────────

_COMP = "compilacao"


def tab_compilar():
    st.header("📊 Compilar arquivos .xlsx")
    st.markdown(
        "Selecione uma pasta local. Cada arquivo é reconhecido pelo modelo cadastrado e suas colunas "
        "são levadas para as **colunas padrão**, tudo em um único `.xlsx`. Arquivos de modelos ainda "
        "desconhecidos aparecem agrupados para você cadastrar o modelo na hora."
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        input_dir = st.text_input(
            "Pasta de entrada",
            placeholder="/Users/usuario/planilhas/medicoes",
            help="Caminho absoluto da pasta com os arquivos .xlsx",
        )
    with col2:
        st.write("")
        recursive = st.checkbox("Incluir subpastas", value=True)

    if st.button("▶ Iniciar compilação", type="primary", use_container_width=True):
        if not input_dir or not Path(input_dir).is_dir():
            st.error("Pasta não encontrada. Verifique o caminho informado.")
        else:
            _run_compilacao(Path(input_dir), recursive)

    comp = st.session_state.get(_COMP)
    if comp:
        _render_compilacao(comp)


def _run_compilacao(input_dir: Path, recursive: bool) -> None:
    from compilador.catalog.loader import load_catalog
    from compilador.compiler.walker import list_xlsx, process_files

    files = list_xlsx(input_dir, recursive)
    total = len(files)
    if total == 0:
        st.session_state.pop(_COMP, None)
        st.warning("Nenhum arquivo .xlsx encontrado na pasta informada.")
        return

    progress = st.progress(0, text=f"📊 Progresso geral: 0 / {total}")
    current_file = st.empty()
    log_placeholder = st.empty()
    results, log_rows = [], []
    for event in process_files(files, load_catalog()):
        r = event.result
        results.append(r)
        log_rows.append({
            "status": _status_icon(r.status),
            "arquivo": Path(r.path).name,
            "formato": r.format_id or "—",
            "linhas": r.rows_extracted,
            "erro": r.error or "",
        })
        progress.progress(event.fraction, text=f"📊 Progresso geral: {event.current} / {event.total}")
        current_file.caption(f"📄 Arquivo atual: **{event.filename}**")
        log_placeholder.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)

    st.session_state[_COMP] = {"results": results, "xlsx": None}
    st.rerun()


def _reprocess_pending(comp: dict) -> None:
    """Reprocessa só os arquivos ainda sem modelo (após cadastrar um modelo novo)."""
    from compilador.catalog.loader import load_catalog
    from compilador.compiler.walker import process_files

    pending = [Path(r.path) for r in comp["results"] if r.status == "unidentified"]
    updated = {e.result.path: e.result for e in process_files(pending, load_catalog())}
    comp["results"] = [updated.get(r.path, r) for r in comp["results"]]
    comp["xlsx"] = None


def _render_compilacao(comp: dict) -> None:
    from compilador.compiler.assembler import assemble_output

    results = comp["results"]
    st.divider()
    st.subheader("📋 Resumo do processamento")
    counts = Counter(r.status for r in results)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ Reconhecidos", counts["ok"])
    m2.metric("⚠️ Revisão recomendada", counts["review"])
    m3.metric("🆕 Sem modelo cadastrado", counts["unidentified"])
    m4.metric("💥 Erros", counts["error"] + counts["skipped"])

    rows = [row for r in results for row in r.rows]
    if comp["xlsx"] is None:
        comp["xlsx"] = assemble_output(rows, results)
    st.download_button(
        label=f"⬇ Baixar compilado.xlsx ({len(rows)} linhas)",
        data=comp["xlsx"],
        file_name="compilado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    pending = [r for r in results if r.status == "unidentified"]
    if pending:
        _render_pendentes(comp, pending)

    with st.expander("Detalhe por arquivo"):
        st.dataframe(pd.DataFrame([{
            "status": _status_icon(r.status),
            "arquivo": Path(r.path).name,
            "modelo": r.format_id or "—",
            "confiança": f"{r.confidence:.2f}" if r.format_id else "—",
            "linhas": r.rows_extracted,
            "erro": r.error or "",
        } for r in results]), use_container_width=True, hide_index=True)


def _render_pendentes(comp: dict, pending: list) -> None:
    import hashlib

    groups: dict[str, list] = {}
    for r in pending:
        groups.setdefault(r.layout_key, []).append(r)

    st.subheader(f"🆕 Modelos ainda não cadastrados ({len(groups)})")
    st.caption(
        "Arquivos com o mesmo layout estão agrupados. Cadastre o modelo uma vez e todos os arquivos "
        "do grupo entram na compilação."
    )
    for i, (layout, files) in enumerate(groups.items()):
        columns = layout.replace("|", " · ")
        title = f"{len(files)} arquivo(s) · colunas: {columns[:110]}{'…' if len(columns) > 110 else ''}"
        with st.expander(title, expanded=len(groups) == 1):
            shown = ", ".join(Path(r.path).name for r in files[:5])
            st.caption(f"Arquivos: {shown}{' …' if len(files) > 5 else ''}")
            key = "grp_" + hashlib.md5(layout.encode()).hexdigest()[:8]
            entry = _learn_ui(Path(files[0].path), key=key, sheet_hint=files[0].sheet_name)
            if entry:
                before = len(pending)
                _reprocess_pending(comp)
                absorbed = before - sum(1 for r in comp["results"] if r.status == "unidentified")
                st.session_state["_flash"] = (
                    f"✅ Modelo '{entry.display_name}' cadastrado. {absorbed} arquivo(s) passaram a ser reconhecidos."
                )
                st.rerun()


# ── Tab: Novo modelo ──────────────────────────────────────────────────────────

def tab_novo_modelo():
    st.header("🧠 Cadastrar novo modelo")
    st.markdown(
        "Envie uma planilha de exemplo. O sistema sugere a correspondência entre as colunas dela e as "
        "**colunas padrão**; você confere, dá um nome e salva. Dali em diante, qualquer planilha com esse "
        "layout é reconhecida automaticamente."
    )
    uploaded = st.file_uploader("Planilha de exemplo (.xlsx)", type=["xlsx"], key="novo_upload")
    if not uploaded:
        return
    entry = _learn_ui(_save_upload(uploaded), key="novo", check_existing=True)
    if entry:
        st.session_state["_flash"] = f"✅ Modelo '{entry.display_name}' cadastrado."
        st.rerun()


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
        st.info("Catálogo vazio. Cadastre modelos na aba 🧠 Novo modelo ou direto ao compilar uma pasta.")

    st.divider()

    # Inspect
    st.subheader("Inspecionar formato")
    fmt_ids = [f.format_id for f in catalog.formats]
    if fmt_ids:
        selected = st.selectbox("Selecionar formato", fmt_ids)
        entry = catalog.get(selected)
        if entry:
            st.json(json.loads(entry.model_dump_json()))
            r1, r2 = st.columns([1, 3])
            confirm = r1.checkbox("Confirmar remoção", key="rm_confirm")
            if r2.button("🗑 Remover este modelo", disabled=not confirm):
                from compilador.catalog.loader import remove_format
                remove_format(selected)
                st.session_state["_flash"] = f"Modelo '{selected}' removido do catálogo."
                st.rerun()
    else:
        st.info("Nenhum formato disponível para inspecionar.")

    st.divider()

    # Standard columns
    st.subheader("Colunas padrão")
    st.caption("Todo modelo é mapeado para estas colunas. Novas colunas são criadas na aba 🧠 Novo modelo.")
    from compilador.catalog.schema import load_schema
    st.dataframe(
        pd.DataFrame([
            {"Coluna": f.label, "Tipo": {"text": "Texto", "number": "Número", "date": "Data"}[f.type],
             "Nome interno": f.name}
            for f in load_schema().fields
        ]),
        use_container_width=True, hide_index=True,
    )

    st.divider()

    # Add new format (advanced)
    with st.expander("Avançado: importar modelo de um arquivo JSON"):
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

    flash = st.session_state.pop("_flash", None)
    if flash:
        st.success(flash)

    tab1, tab_novo, tab2, tab3, tab4 = st.tabs(
        ["📊 Compilar .xlsx", "🧠 Novo modelo", "📄 Converter PDF", "📚 Catálogo", "⚙️ Configuração"]
    )

    with tab1:
        tab_compilar()
    with tab_novo:
        tab_novo_modelo()
    with tab2:
        tab_converter_pdf()
    with tab3:
        tab_catalogo()
    with tab4:
        tab_configuracao()


main()
