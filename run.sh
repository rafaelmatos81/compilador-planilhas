#!/bin/bash
# ╔══════════════════════════════════════════════╗
# ║  Compilador de Planilhas — Launcher Linux   ║
# ╚══════════════════════════════════════════════╝

cd "$(dirname "$0")"

VENV=".venv"
PYTHON_BIN="$VENV/bin/python"
STREAMLIT_BIN="$VENV/bin/streamlit"

echo ""
echo "  Compilador de Planilhas"
echo "  ─────────────────────────────────────"
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
    echo "  ERRO: Python 3.10+ não encontrado."
    echo ""
    echo "  Ubuntu/Debian:  sudo apt install python3.11 python3.11-venv"
    echo "  Fedora:         sudo dnf install python3.11"
    echo ""
    exit 1
fi
echo "  Python: $($PY --version)"

# ── 2. Criar ambiente virtual ────────────────────────────────────────────────
if [[ ! -f "$PYTHON_BIN" ]]; then
    echo ""
    echo "  Configurando ambiente (primeira vez)..."

    # python3-venv pode não estar instalado no Ubuntu
    if ! "$PY" -m venv --help &>/dev/null 2>&1; then
        echo "  Instalando python3-venv..."
        sudo apt-get install -y python3-venv 2>/dev/null || \
            sudo dnf install -y python3-venv 2>/dev/null || true
    fi

    "$PY" -m venv "$VENV"
    if [[ $? -ne 0 ]]; then
        echo "  ERRO ao criar ambiente virtual."
        exit 1
    fi
fi

# ── 3. Dependências ──────────────────────────────────────────────────────────
echo "  Verificando dependências..."
"$PYTHON_BIN" -m pip install -e . -q --disable-pip-version-check

# ── 4. Iniciar ───────────────────────────────────────────────────────────────
echo ""
echo "  App disponível em: http://localhost:8501"
echo "  Para encerrar: Ctrl+C"
echo ""

# Suprimir prompt de e-mail do Streamlit
CREDS="$HOME/.streamlit/credentials.toml"
if [[ ! -f "$CREDS" ]]; then
    mkdir -p "$HOME/.streamlit"
    printf '[general]\nemail = ""\n' > "$CREDS"
fi

# Abrir navegador depois de 3s (se disponível)
if command -v xdg-open &>/dev/null; then
    (sleep 3 && xdg-open "http://localhost:8501") &
fi

"$STREAMLIT_BIN" run src/compilador/app.py
