from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from charset_normalizer import from_path

from services.ocr_client import OcrClient
from utils.errors import FileProcessError


class ContentExtractor:
    """文件内容提取服务。"""

    DOC_EXTS = {".doc", ".docx", ".rtf", ".excel"}
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
    TEXT_EXTS = {".txt", ".md"}

    def __init__(self, ocr_client: OcrClient | None = None) -> None:
        self.ocr_client = ocr_client or OcrClient()

    def extract(self, file_path: str, ocr_config: dict[str, Any] | None = None) -> str:
        ext = Path(file_path).suffix.lower()

        if ext in self.DOC_EXTS:
            return self._extract_doc(file_path)
        if ext == ".pdf":
            return self._extract_by_ocr(file_path, ocr_config)
        if ext in self.IMAGE_EXTS:
            return self._extract_by_ocr(file_path, ocr_config)
        if ext in self.TEXT_EXTS:
            return self._extract_text(file_path)

        raise FileProcessError(f"不支持的文件类型: {ext}")

    def _extract_doc(self, file_path: str) -> str:
        try:
            mammoth = importlib.import_module("mammoth")
        except ImportError as exc:
            raise FileProcessError("缺少依赖 mammoth，请先安装") from exc

        with open(file_path, "rb") as f:
            return mammoth.convert_to_markdown(f).value

    def _extract_text(self, file_path: str) -> str:
        res = from_path(file_path).best()
        return str(res) if res else "读取失败"

    def _extract_by_ocr(self, file_path: str, ocr_config: dict[str, Any] | None) -> str:
        ocr_results = self.ocr_client.parse(file_path=file_path, ocr_config=ocr_config)
        return self._format_ocr_to_markdown(ocr_results)

    def _format_ocr_to_markdown(self, ocr_results: list[dict[str, Any]]) -> str:
        if not ocr_results:
            return "[OCR 未识别到文字内容]"

        pages = []
        for page in ocr_results:
            idx = page.get("page_index", "?")
            lines = page.get("rec_texts", [])
            clean_text = "\n".join(line.strip() for line in lines if str(line).strip())
            pages.append(f"### 第 {idx} 页\n\n{clean_text}")

        return "\n\n---\n\n".join(pages)
