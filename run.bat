@echo off
:: ============================================================
::  Compilador de Planilhas — Launcher Windows
::  Duplo clique para abrir
:: ============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Compilador de Planilhas

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "PYTHON_BIN=%VENV%\Scripts\python.exe"
set "STREAMLIT_BIN=%VENV%\Scripts\streamlit.exe"

cls
echo.
echo   ==========================================
echo     Compilador de Planilhas
echo   ==========================================
echo.

:: ── 1. Localizar Python 3.10+ ────────────────────────────────────────────────
set "PY="
for %%c in (python3.13 python3.12 python3.11 python3.10 python3 python) do (
    if not defined PY (
        where %%c >nul 2>&1 && (
            for /f "tokens=*" %%v in ('%%c -c "import sys; print(sys.version_info >= (3,10))" 2^>nul') do (
                if "%%v"=="True" set "PY=%%c"
            )
        )
    )
)

if not defined PY (
    echo   ERRO: Python 3.10 ou superior nao encontrado.
    echo.
    echo   Baixe Python em: https://www.python.org/downloads/
    echo   IMPORTANTE: marque "Add Python to PATH" durante a instalacao.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('!PY! --version 2^>^&1') do echo   Python: %%v

:: ── 2. Criar ambiente virtual ─────────────────────────────────────────────────
if not exist "%PYTHON_BIN%" (
    echo.
    echo   Configurando ambiente ^(primeira vez^)...
    !PY! -m venv "%VENV%"
    if errorlevel 1 (
        echo   ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
)

:: ── 3. Instalar dependências ──────────────────────────────────────────────────
echo   Verificando dependencias...
"%PYTHON_BIN%" -m pip install -e "%ROOT%." -q --disable-pip-version-check
if errorlevel 1 (
    echo   ERRO ao instalar dependencias.
    pause
    exit /b 1
)

:: ── 4. Suprimir prompt de e-mail do Streamlit ────────────────────────────────
set "CREDS=%USERPROFILE%\.streamlit\credentials.toml"
if not exist "%CREDS%" (
    if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
    (echo [general] & echo email = "") > "%CREDS%"
)

:: ── 5. Abrir navegador e iniciar app ─────────────────────────────────────────
echo.
echo   Iniciando... O navegador abrira em: http://localhost:8501
echo   Para encerrar: feche esta janela.
echo.

:: Abre o navegador após 4 segundos
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8501"

"%STREAMLIT_BIN%" run "%ROOT%src\compilador\app.py"

pause
