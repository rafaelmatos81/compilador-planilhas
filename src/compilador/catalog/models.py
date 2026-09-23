from pydantic import BaseModel, Field
from typing import Literal, Optional


class HeaderAnchor(BaseModel):
    text: str
    match_mode: Literal["exact", "contains", "fuzzy"] = "contains"
    scope: Literal["any_cell", "first_N_rows", "column_header_row"] = "first_N_rows"
    first_N: int = 10
    weight: float = 1.0
    required: bool = False


class ColumnAnchor(BaseModel):
    canonical_name: str
    aliases: list[str]
    fuzzy_threshold: int = 80
    weight: float = 1.0
    required: bool = False


class CellAnchor(BaseModel):
    row: Optional[int] = None
    col: Optional[int] = None
    text: str
    match_mode: Literal["exact", "contains", "fuzzy"] = "contains"
    weight: float = 0.5


class StructureHints(BaseModel):
    min_columns: int = 2
    max_columns: Optional[int] = None
    min_data_rows: int = 1
    has_merged_header: bool = False


class DetectionRules(BaseModel):
    header_anchors: list[HeaderAnchor] = Field(default_factory=list)
    column_anchors: list[ColumnAnchor] = Field(default_factory=list)
    cell_anchors: list[CellAnchor] = Field(default_factory=list)
    structure_hints: StructureHints = Field(default_factory=StructureHints)


class ExtractionRules(BaseModel):
    header_row: int = 1
    data_start_row: int = 2
    sheet_selector: Literal["first", "named", "pattern"] = "first"
    sheet_name: Optional[str] = None
    sheet_pattern: Optional[str] = None
    column_map: dict[str, str] = Field(default_factory=dict)
    skip_rows_containing: list[str] = Field(default_factory=list)


class FormatEntry(BaseModel):
    format_id: str
    display_name: str
    agency: str
    document_type: str
    version: str = ""
    description: str = ""
    detection: DetectionRules = Field(default_factory=DetectionRules)
    extraction: ExtractionRules = Field(default_factory=ExtractionRules)


class CatalogManifest(BaseModel):
    catalog_version: str = "1.0"
    last_updated: str = ""
    formats: list[FormatEntry] = Field(default_factory=list)

    def get(self, format_id: str) -> Optional[FormatEntry]:
        for f in self.formats:
            if f.format_id == format_id:
                return f
        return None

    def ids(self) -> list[str]:
        return [f.format_id for f in self.formats]
