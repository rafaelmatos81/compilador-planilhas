class CompiladorError(Exception):
    pass


class UnreadableFile(CompiladorError):
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot read {path}: {reason}")


class LowConfidence(CompiladorError):
    def __init__(self, format_id: str, confidence: float):
        self.format_id = format_id
        self.confidence = confidence
        super().__init__(f"Low confidence {confidence:.2f} for format {format_id}")


class CatalogError(CompiladorError):
    pass


class ExtractionError(CompiladorError):
    pass
