from __future__ import annotations

from typing import Any

from services.content_extractor import ContentExtractor


_extractor = ContentExtractor()


def extract_content(file_path: str, ocr_config: dict[str, Any] | None = None) -> str:
    """兼容入口：转发到 ContentExtractor。"""
    return _extractor.extract(file_path=file_path, ocr_config=ocr_config)