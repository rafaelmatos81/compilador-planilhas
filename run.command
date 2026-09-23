#!/bin/bash
# ╔══════════════════════════════════════════════╗
# ║  Compilador de Planilhas — Launcher macOS   ║
# ║  Duplo clique para abrir                    ║
# ╚══════════════════════════════════════════════╝

# Vai para o diretório do script (necessário para duplo clique no Finder)
cd "$(dirname "$0")"

VENV=".venv"
PYTHON_BIN="$VENV/bin/python"
STREAMLIT_BIN="$VENV/bin/streamlit"

clear
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║      Compilador de Planilhas         ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Localizar Python 3.10+ ────────────────────────────────────────────────
_find_python() {
    for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &>/dev/null; then
            ok=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null)
            [[ "$ok" == "True" ]] && { echo "$cmd"; return 0; }
        fi
    done
    return 1
}

PY=$(_find_python)
if [[ -z "$PY" ]]; then
    echo "  ❌  Python 3.10 ou superior não encontrado."
    echo ""
    echo "  Instale Python em: https://www.python.org/downloads/"
    echo "  Marque a opção 'Add to PATH' e depois abra este arquivo novamente."
    echo ""
    open "https://www.python.org/downloads/" 2>/dev/null
    echo ""
    read -rp "  Pressione Enter para fechar..."
    exit 1
fi
echo "  ✅  $($PY --version)"

# ── 2. Criar ambiente virtual (apenas na primeira vez) ───────────────────────
if [[ ! -f "$PYTHON_BIN" ]]; then
    echo ""
    echo "  ⏳  Primeira execução — configurando o ambiente..."
    echo "      (pode demorar alguns minutos)"
    "$PY" -m venv "$VENV"
    if [[ $? -ne 0 ]]; then
        echo "  ❌  Falha ao criar ambiente virtual."
        read -rp "  Pressione Enter para fechar..."
        exit 1
    fi
fi

# ── 3. Instalar / atualizar dependências ─────────────────────────────────────
echo ""
echo "  ⏳  Verificando dependências..."
"$PYTHON_BIN" -m pip install -e . -q --disable-pip-version-check
if [[ $? -ne 0 ]]; then
    echo "  ❌  Erro ao instalar dependências."
    echo "      Tente abrir o Terminal e executar manualmente:"
    echo "      pip3 install -e ."
    read -rp "  Pressione Enter para fechar..."
    exit 1
fi

# ── 4. Suprimir prompt de e-mail do Streamlit ────────────────────────────────
CREDS="$HOME/.streamlit/credentials.toml"
if [[ ! -f "$CREDS" ]]; then
    mkdir -p "$HOME/.streamlit"
    printf '[general]\nemail = ""\n' > "$CREDS"
fi

# ── 5. Iniciar app e abrir navegador ─────────────────────────────────────────
echo ""
echo "  ✅  Iniciando..."
echo "      O navegador abrirá automaticamente em: http://localhost:8501"
echo "      Para encerrar: feche esta janela ou pressione Ctrl+C"
echo ""

(sleep 3 && open "http://localhost:8501") &
"$STREAMLIT_BIN" run src/compilador/app.py
