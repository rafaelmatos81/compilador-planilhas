from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    catalog_path: Path = Path(__file__).parent.parent.parent / "catalog" / "formats.json"
    confidence_high: float = 0.85
    confidence_medium: float = 0.60
    confidence_low: float = 0.40
    ocr_lang: str = "por"
    ocr_dpi: int = 300
    log_level: str = "INFO"

    model_config = {"env_prefix": "COMPILADOR_", "env_file": ".env"}


settings = Settings()
