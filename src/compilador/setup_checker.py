"""Verificação e instalação automática de dependências do sistema e Python."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ── Detecção ──────────────────────────────────────────────────────────────────

def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _os() -> str:
    return platform.system()  # "Darwin", "Linux", "Windows"


def check_brew() -> bool:
    return shutil.which("brew") is not None


def check_poppler() -> bool:
    return shutil.which("pdftoppm") is not None or shutil.which("pdfinfo") is not None


def check_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def check_python_pkg(import_name: str) -> bool:
    try:
        __import__(import_name)
        return True
    except ImportError:
        return False


# Pacotes Python necessários: (nome_exibição, nome_import)
_PYTHON_DEPS = [
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("pdfplumber", "pdfplumber"),
    ("rapidfuzz", "rapidfuzz"),
    ("pydantic", "pydantic"),
    ("loguru", "loguru"),
    ("typer", "typer"),
    ("rich", "rich"),
    ("camelot-py", "camelot"),
    ("pdf2image", "pdf2image"),
    ("pytesseract", "pytesseract"),
]


def check_all_python_packages() -> dict[str, bool]:
    return {name: check_python_pkg(imp) for name, imp in _PYTHON_DEPS}


def get_missing_system_deps() -> list[str]:
    """Retorna lista de nomes amigáveis de deps do sistema ausentes."""
    missing = []
    if not check_poppler():
        missing.append("Poppler")
    if not check_tesseract():
        missing.append("Tesseract OCR")
    return missing


# ── Comandos de instalação ────────────────────────────────────────────────────

def _install_cmd(tool: str) -> tuple[list[str] | None, str | None]:
    """Retorna (cmd, instrucao_manual). cmd=None se instalação automática indisponível."""
    os_name = _os()

    if tool == "poppler":
        if os_name == "Darwin":
            if not check_brew():
                return None, "Instale o Homebrew primeiro: https://brew.sh — depois execute: brew install poppler"
            return ["brew", "install", "poppler"], None
        if os_name == "Linux":
            return ["sudo", "apt-get", "install", "-y", "poppler-utils"], None
        return None, "Windows: baixe em https://github.com/oschwartz10612/poppler-windows/releases e adicione ao PATH."

    if tool == "tesseract":
        if os_name == "Darwin":
            if not check_brew():
                return None, "Instale o Homebrew primeiro: https://brew.sh — depois execute: brew install tesseract tesseract-lang"
            return ["brew", "install", "tesseract", "tesseract-lang"], None
        if os_name == "Linux":
            return ["sudo", "apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-por"], None
        return None, "Windows: baixe em https://github.com/UB-Mannheim/tesseract/wiki"

    if tool == "python_packages":
        # Instala core + tenta extras opcionais (pdf, ocr)
        return [sys.executable, "-m", "pip", "install", "-e", f"{_project_root()}[full]"], None

    if tool == "python_packages_core":
        return [sys.executable, "-m", "pip", "install", "-e", str(_project_root())], None

    return None, f"Ferramenta desconhecida: {tool}"


# ── Execução com streaming de saída ──────────────────────────────────────────

def run_streaming(cmd: list[str]) -> Iterator[str]:
    """
    Executa um comando e gera linhas de saída em tempo real.
    A última linha gerada é '__done__:0' (sucesso) ou '__done__:1' (erro).
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in iter(proc.stdout.readline, ""):
            stripped = line.rstrip()
            if stripped:
                yield stripped
        proc.wait()
        yield f"__done__:{proc.returncode}"
    except FileNotFoundError:
        yield f"Comando não encontrado: {cmd[0]}"
        yield "__done__:1"
    except Exception as e:
        yield f"Erro: {e}"
        yield "__done__:1"


def install_tool(tool: str) -> tuple[list[str] | None, str | None]:
    """Retorna (cmd, instrucao_manual) para a ferramenta solicitada."""
    return _install_cmd(tool)
