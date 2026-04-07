from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class FileStorage(ABC):
    @abstractmethod
    def save(self, file_id: str, filename: str, content_bytes: bytes) -> str:
        """保存文件并返回绝对路径。"""


class LocalFileStorage(FileStorage):
    def __init__(self, upload_dir: Path) -> None:
        self.upload_dir = upload_dir.resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file_id: str, filename: str, content_bytes: bytes) -> str:
        ext = Path(filename).suffix.lower() or ".bin"
        save_path = (self.upload_dir / f"{file_id}{ext}").resolve()
        with open(save_path, "wb") as f:
            f.write(content_bytes)
        return str(save_path)
