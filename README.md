# Compilador de Planilhas

Sistema para compilação inteligente de planilhas e conversão de PDFs para administração contratual de obras de infraestrutura civil (DNIT, SABESP, IPHAN, VALE, CEMIG).

## Funcionalidades

- **Compilação de .xlsx**: processa uma pasta inteira de planilhas, identifica automaticamente o modelo de cada arquivo (mesmo vindo de fontes diferentes) e consolida tudo em um único `.xlsx` com **colunas padrão** e rastreabilidade.
- **Aprendizado de modelos**: a partir de uma planilha de exemplo, o sistema sugere a correspondência entre as colunas dela e as colunas padrão; você confere, dá um nome e o modelo fica salvo no catálogo. Arquivos de modelos ainda desconhecidos aparecem agrupados por layout durante a compilação, para cadastro na hora.
- **Conversão de PDF**: usa o catálogo de formatos para reconhecer o padrão de um PDF e extrair as tabelas (com OCR como fallback), gerando `.xlsx` compatível com a compilação.
- **Catálogo extensível**: modelos novos são cadastrados pela interface (ou via JSON), sem alterar código.

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

## Como cadastrar um modelo novo

**Pela interface (recomendado):** na aba **🧠 Novo modelo**, envie uma planilha de exemplo, confira a linha do cabeçalho e a coluna padrão sugerida para cada coluna, dê um nome e salve. Também é possível cadastrar direto na aba **📊 Compilar**: arquivos sem modelo aparecem agrupados por layout, e ao salvar o modelo todos os arquivos do grupo entram na compilação.

Colunas padrão (Item, Descrição, Unidade, Quantidade, Valor unitário, Valor total, Data…) ficam em `catalog/canonical_fields.json` e podem ser ampliadas na própria tela de cadastro. Colunas de tipo Número e Data saem no `.xlsx` como número e data reais, não como texto. Se um mesmo título aparece em duas colunas (dois "Valor"), o modelo os distingue pela ordem (`Valor`, `Valor #2`).

## Adicionar formato manualmente (avançado)

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
├── catalog/formats.json        # Catálogo de modelos (editável)
├── catalog/canonical_fields.json  # Colunas padrão (criado ao adicionar uma nova coluna)
├── tests/                      # pytest: aprender modelo -> compilar
└── src/compilador/
    ├── app.py                  # Interface Streamlit
    ├── cli.py                  # CLI alternativo (Typer)
    ├── catalog/                # Modelos, CRUD do catálogo e colunas padrão (schema.py)
    ├── learner.py              # Aprende um modelo a partir de uma planilha de exemplo
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
| < 0.60 | Sem match | Arquivo fica "sem modelo cadastrado" e é oferecido para cadastro |

## Testes

```bash
pip install -e ".[dev]"
pytest
```
