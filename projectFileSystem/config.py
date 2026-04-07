
"""项目配置。

说明：
1. 通过 PROJECT_CONFIGS 按 project_id 维护需要文件、要素、OCR模型。
2. 示例仅保留结构，真实环境请通过环境变量注入敏感信息。
"""

import os
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv


_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")


DEFAULT_OCR_CONFIG = {
    "provider": "remote_api",
    "model_name": os.getenv("OCR_MODEL_NAME", "pp-ocrv5"),
    "endpoint": os.getenv("OCR_SERVICE_URL", "http://127.0.0.1:8001"),
    "api_key": os.getenv("OCR_API_KEY", ""),
    "timeout": int(os.getenv("OCR_TIMEOUT", "180")),
}


DEFAULT_LLM_CONFIG = {
    "model": os.getenv("LLM_MODEL", "google/gemini-3-flash-preview"),
    "base_url": os.getenv("LLM_BASE_URL", "http://120.25.254.115:3000/v1"),
    "api_key": os.getenv("LLM_API_KEY", "sk-UCOcvrpHSjEfQMdcUcIRTHo5BV9W6UE1hTHsW1hPjCpQwZSO"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0")),
    "timeout": int(os.getenv("LLM_TIMEOUT", "120")),
}


PROJECT_CONFIGS = {
    "demo-project": {
        "project_id": "demo-project",
        "ocr": deepcopy(DEFAULT_OCR_CONFIG),
        "llm": deepcopy(DEFAULT_LLM_CONFIG),
        "need_files": [
            {
                "file_type": "保函",
                "available": True,
                "aliases": ["保函格式", "履约保函"],
                "elements": [
                    {
                        "element_key": "partA",
                        "description": "甲方名称",
                    },
                    {
                        "element_key": "partB",
                        "description": "乙方名称",
                    },
                ],
            },
            {
                "file_type": "合同",
                "available": True,
                "aliases": ["施工合同", "采购合同"],
                "elements": [
                    {
                        "element_key": "sign_date",
                        "description": "签订日期",
                    },
                    {
                        "element_key": "amount",
                        "description": "合同金额",
                    },
                ],
            },
        ],
    }
}


DEFAULT_PROJECT_ID = "demo-project"