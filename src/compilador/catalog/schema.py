"""Colunas padrão (canônicas) da planilha compilada.

Todo modelo cadastrado mapeia as colunas da planilha de origem para estes campos,
e a saída compilada usa apenas eles. A lista é editável em catalog/canonical_fields.json.
"""
import json
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field
from .loader import _DEFAULT_CATALOG
from ..common.exceptions import CatalogError
from ..identifier.normalizer import slugify

_DEFAULT_SCHEMA_PATH = _DEFAULT_CATALOG.parent / "canonical_fields.json"


class CanonicalField(BaseModel):
    name: str
    label: str
    type: Literal["text", "number", "date"] = "text"
    aliases: list[str] = Field(default_factory=list)


class CanonicalSchema(BaseModel):
    fields: list[CanonicalField] = Field(default_factory=list)

    def get(self, name: str) -> Optional[CanonicalField]:
        return next((f for f in self.fields if f.name == name), None)

    def label(self, name: str) -> str:
        f = self.get(name)
        return f.label if f else name

    def names(self) -> list[str]:
        return [f.name for f in self.fields]


_DEFAULT_FIELDS = [
    {"name": "item", "label": "Item", "aliases": ["item", "it", "nº item", "n item", "seq", "sequencia"]},
    {"name": "codigo", "label": "Código", "aliases": ["codigo", "cod", "referencia", "ref", "cod servico"]},
    {"name": "descricao", "label": "Descrição",
     "aliases": ["descricao", "descricao do servico", "servico", "discriminacao", "especificacao"]},
    {"name": "unidade", "label": "Unidade", "aliases": ["un", "und", "unid", "unidade", "u.m."]},
    {"name": "qtd_medida", "label": "Quantidade", "type": "number",
     "aliases": ["quantidade", "qtd", "qtde", "quant", "qtd medida", "quantidade medida"]},
    {"name": "valor_unit", "label": "Valor unitário", "type": "number",
     "aliases": ["valor unitario", "preco unitario", "p. unit.", "pu", "vl unit", "custo unitario"]},
    {"name": "valor_total", "label": "Valor total", "type": "number",
     "aliases": ["total", "valor total", "preco total", "vl total", "valor"]},
    {"name": "data", "label": "Data", "type": "date", "aliases": ["data", "dt", "dia", "data da medicao"]},
    {"name": "turno", "label": "Turno", "aliases": ["turno"]},
    {"name": "responsavel", "label": "Responsável", "aliases": ["responsavel", "resp"]},
    {"name": "atividade", "label": "Atividade", "aliases": ["atividade", "atividades"]},
    {"name": "equipe", "label": "Equipe", "aliases": ["equipe"]},
    {"name": "observacoes", "label": "Observações",
     "aliases": ["observacoes", "observacao", "obs", "comentarios"]},
]


def load_schema(path: Path | str | None = None) -> CanonicalSchema:
    schema_path = Path(path) if path else _DEFAULT_SCHEMA_PATH
    if not schema_path.exists():
        return CanonicalSchema.model_validate({"fields": _DEFAULT_FIELDS})
    try:
        return CanonicalSchema.model_validate(json.loads(schema_path.read_text(encoding="utf-8")))
    except Exception as e:
        raise CatalogError(f"Failed to load canonical fields from {schema_path}: {e}") from e


def save_schema(schema: CanonicalSchema, path: Path | str | None = None) -> None:
    schema_path = Path(path) if path else _DEFAULT_SCHEMA_PATH
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        json.dumps(schema.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_field(
    label: str,
    type: Literal["text", "number", "date"] = "text",
    path: Path | str | None = None,
) -> CanonicalField:
    """Cria uma nova coluna padrão. O nome interno é derivado do rótulo."""
    label = label.strip()
    name = slugify(label)
    if not name:
        raise CatalogError("Informe um nome para a coluna.")
    schema = load_schema(path)
    if schema.get(name):
        raise CatalogError(f"A coluna padrão '{schema.label(name)}' já existe.")
    field_ = CanonicalField(name=name, label=label, type=type, aliases=[label])
    schema.fields.append(field_)
    save_schema(schema, path)
    return field_
