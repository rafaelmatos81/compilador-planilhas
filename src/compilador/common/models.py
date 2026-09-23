from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"      # >= 0.85
    MEDIUM = "MEDIUM"  # 0.60 - 0.84
    LOW = "LOW"        # 0.40 - 0.59
    NONE = "NONE"      # < 0.40


@dataclass
class ParsedTable:
    rows: list[list[str]]
    sheet_name: str = ""
    source_file: str = ""

    def __len__(self) -> int:
        return len(self.rows)


@dataclass
class ScoredMatch:
    format_id: str
    confidence: float
    matched_anchors: list[str] = field(default_factory=list)

    @property
    def level(self) -> ConfidenceLevel:
        if self.confidence >= 0.85:
            return ConfidenceLevel.HIGH
        if self.confidence >= 0.60:
            return ConfidenceLevel.MEDIUM
        if self.confidence >= 0.40:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.NONE


@dataclass
class CanonicalRow:
    source_file: str
    source_sheet: str
    format_id: str
    confidence: float
    ocr_used: bool
    needs_review: bool
    row_index_in_source: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileResult:
    path: str
    sheets_processed: int = 0
    rows_extracted: int = 0
    format_id: Optional[str] = None
    confidence: float = 0.0
    ocr_used: bool = False
    needs_review: bool = False
    error: Optional[str] = None
    skipped: bool = False

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.skipped:
            return "skipped"
        if self.confidence < 0.40:
            return "unidentified"
        if self.needs_review or self.confidence < 0.85:
            return "review"
        return "ok"

    @property
    def icon(self) -> str:
        return {
            "ok": "✅",
            "review": "⚠️",
            "unidentified": "❌",
            "error": "❌",
            "skipped": "⏭️",
        }.get(self.status, "❓")


@dataclass
class ProgressEvent:
    current: int
    total: int
    filename: str
    result: Optional[FileResult] = None

    @property
    def fraction(self) -> float:
        return self.current / self.total if self.total > 0 else 0.0
