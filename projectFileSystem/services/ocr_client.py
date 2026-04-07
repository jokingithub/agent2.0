from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from utils.errors import FileProcessError
from utils.logging import get_logger


class OcrClient:
    """OCR HTTP 客户端。"""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def parse(self, file_path: str, ocr_config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cfg = ocr_config or {}
        endpoint = cfg.get("endpoint") or os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001")
        timeout = int(cfg.get("timeout") or os.getenv("OCR_TIMEOUT", "120"))
        model_name = cfg.get("model_name") or os.getenv("OCR_MODEL_NAME", "default-ocr")
        api_key = cfg.get("api_key") or os.getenv("OCR_API_KEY", "")

        try:
            return self._request_ocr(file_path, endpoint, timeout, model_name, api_key)
        except Exception as exc:
            self.logger.error("OCR请求异常: %s", exc)
            raise FileProcessError(f"OCR调用失败: {exc}") from exc

    def _request_ocr(
        self,
        file_path: str,
        endpoint: str,
        timeout: int,
        model_name: str,
        api_key: str,
    ) -> list[dict[str, Any]]:
        with open(file_path, "rb") as f:
            files = {"file": (Path(file_path).name, f, "application/octet-stream")}
            data = {"batch_size": 4, "model_name": model_name}
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            response = requests.post(
                f"{endpoint}/ocr/file",
                files=files,
                data=data,
                headers=headers,
                timeout=timeout,
            )

        payload = response.json() if response.content else {}
        if response.status_code == 200 and payload.get("success"):
            return payload.get("data") or []

        detail = f"status={response.status_code}, body={response.text[:800]}"
        raise FileProcessError(f"OCR接口返回异常: {detail}")
