from langchain_openai import ChatOpenAI
import os
from pathlib import Path

def _load_env_file() -> None:
    """轻量加载 .env（仅在变量未设置时生效）。"""
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if not root_env.exists():
        return

    for line in root_env.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

_load_env_file()

def get_model(model_choice: str = "high") -> ChatOpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("未读取到 OPENAI_API_KEY，请在环境变量或 .env 文件中配置。")
    model = {
        "high": "google/gemini-3-flash-preview",
        "medium": "google/gemini-2.5-pro-preview",
        "low": "google/gemini-1.5-pro-preview",
    }
    return ChatOpenAI(
        model=model.get(model_choice, "google/gemini-3-flash-preview"),
        temperature=0,
        api_key=api_key,
        base_url=os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
    )