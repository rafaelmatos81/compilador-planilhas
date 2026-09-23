# Compilador de Planilhas

Sistema para compilação inteligente de planilhas e conversão de PDFs para administração contratual de obras de infraestrutura civil (DNIT, SABESP, IPHAN, VALE, CEMIG).

## Funcionalidades

- **Compilação de .xlsx**: processa uma pasta inteira de planilhas, identifica automaticamente o formato de cada arquivo (mesmo vindo de fontes diferentes) e consolida tudo em um único `.xlsx` com rastreabilidade.
- **Conversão de PDF**: usa o catálogo de formatos para reconhecer o padrão de um PDF e extrair as tabelas (com OCR como fallback), gerando `.xlsx` compatível com a compilação.
- **Catálogo extensível**: novos formatos são adicionados via JSON, sem alterar código.

## Instalação

### Pré-requisitos

- Python 3.10+
- [Poppler](https://poppler.freedesktop.org/) (para pdf2image):
  - macOS: `brew install poppler`
  - Ubuntu: `sudo apt install poppler-utils`
- [Tesseract OCR](https://tesseract-ocr.github.io/) + pacote de idioma português (para OCR):
  - macOS: `brew install tesseract tesseract-lang`
  - Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-por`

### Instalar o pacote

```bash
cd compilador_planilhas
pip install -e .
```

> Para instalar sem as dependências opcionais de OCR, você pode instalar manualmente apenas as libs necessárias.

## Uso

### Interface gráfica (recomendado)

```bash
streamlit run src/compilador/app.py
```

Abre automaticamente no navegador em `http://localhost:8501`.

### CLI

```bash
# Compilar pasta de .xlsx
compilador compile ./medicoes/ ./saida/compilado.xlsx

# Modo teste (apenas 5 arquivos)
compilador compile ./medicoes/ ./saida/compilado.xlsx --sample 5 --dry-run

# Converter PDF(s)
compilador convert-pdf ./boletins/medicao_003.pdf

# Identificar formato de um arquivo
compilador identify ./arquivo.xlsx --top 3

# Gerenciar catálogo
compilador catalog list
compilador catalog inspect dnit_boletim_medicao_v1
compilador catalog add ./novo_formato.json
compilador catalog validate
compilador catalog test dnit_boletim_medicao_v1 ./arquivo.xlsx
```

## Adicionar novo formato

1. Crie um arquivo JSON seguindo o schema (use `catalog/formats.json` como referência):

```json
{
  "format_id": "meu_orgao_tipo_v1",
  "display_name": "Nome do Formato",
  "agency": "ORGAO",
  "document_type": "MEDICAO",
  "version": "2024",
  "description": "...",
  "detection": { ... },
  "extraction": { ... }
}
```

2. Valide e adicione:

```bash
compilador catalog add ./meu_orgao_tipo_v1.json
compilador catalog test meu_orgao_tipo_v1 ./arquivo_amostra.xlsx
```

## Estrutura do projeto

```
compilador_planilhas/
├── catalog/formats.json        # Catálogo de formatos (editável)
└── src/compilador/
    ├── app.py                  # Interface Streamlit
    ├── cli.py                  # CLI alternativo (Typer)
    ├── catalog/                # Modelos e CRUD do catálogo
    ├── identifier/             # Algoritmo de identificação de formato
    ├── compiler/               # Leitura, extração e montagem de .xlsx
    ├── pdf_converter/          # Pipeline PDF (pdfplumber → camelot → OCR)
    └── common/                 # Modelos, exceções e logging compartilhados
```

## Thresholds de confiança

| Confiança | Significado | Ação |
|-----------|-------------|------|
| ≥ 0.85 | Alta | Extrai normalmente |
| 0.60–0.84 | Média | Extrai, marca `needs_review` |
| 0.40–0.59 | Baixa | Extrai com aviso `LOW_CONFIDENCE` |
| < 0.40 | Sem match | Reporta como não identificado |
