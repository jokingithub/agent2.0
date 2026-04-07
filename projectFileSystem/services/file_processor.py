from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

from Schema import ProjectConfig, ProjectStatus, StoredFile
from element_extra import extract_elements_by_config
from file_classfly import classify_file_by_config
from services.content_extractor import ContentExtractor
from services.storage import FileStorage


class ProjectFileRepository(ABC):
    @abstractmethod
    def add_file(self, project_id: str, item: StoredFile) -> None:
        """新增/更新文件记录。"""

    @abstractmethod
    def list_files(self, project_id: str) -> list[StoredFile]:
        """列出项目文件。"""

    @abstractmethod
    def delete_project(self, project_id: str) -> bool:
        """删除项目文件。"""

    @abstractmethod
    def get_by_file_id(self, file_id: str) -> StoredFile | None:
        """按 file_id 查找任意历史文件记录，用于内容缓存。"""


class InMemoryProjectRepository(ProjectFileRepository):
    def __init__(self) -> None:
        self._data: dict[str, list[StoredFile]] = {}

    def add_file(self, project_id: str, item: StoredFile) -> None:
        self._data.setdefault(project_id, []).append(item)

    def list_files(self, project_id: str) -> list[StoredFile]:
        return self._data.get(project_id, [])

    def delete_project(self, project_id: str) -> bool:
        if project_id not in self._data:
            return False
        del self._data[project_id]
        return True

    def get_by_file_id(self, file_id: str) -> StoredFile | None:
        for files in self._data.values():
            for item in files:
                if item.file_id == file_id:
                    return item
        return None


class FileProcessor:
    """文件处理总流程。"""

    def __init__(
        self,
        storage: FileStorage,
        extractor: ContentExtractor,
        repository: ProjectFileRepository,
    ) -> None:
        self.storage = storage
        self.extractor = extractor
        self.repository = repository

    def process(self, project_cfg: ProjectConfig, filename: str, content_bytes: bytes) -> dict[str, Any]:
        file_id = self._build_file_id(content_bytes)
        cached_item = self.repository.get_by_file_id(file_id)

        if cached_item:
            file_path = cached_item.stored_path
            content = cached_item.content
            cache_hit = True
        else:
            file_path = self.storage.save(file_id=file_id, filename=filename, content_bytes=content_bytes)
            content = self.extractor.extract(file_path=file_path, ocr_config=project_cfg.ocr.model_dump())
            cache_hit = False

        file_type = classify_file_by_config(
            content=content,
            filename=filename,
            file_configs=project_cfg.need_files,
            llm_config=project_cfg.llm,
        )
        matched_cfg = next((cfg for cfg in project_cfg.need_files if cfg.file_type == file_type), None)
        elements = extract_elements_by_config(
            content=content,
            file_type_config=matched_cfg,
            llm_config=project_cfg.llm,
        )

        stored = StoredFile(
            file_id=file_id,
            project_id=project_cfg.project_id,
            original_name=filename,
            stored_path=file_path,
            file_type=file_type,
            content=content,
            elements=elements,
        )
        self.repository.add_file(project_cfg.project_id, stored)
        return self._build_response(project_cfg.project_id, file_id, filename, file_type, elements, content, cache_hit)

    def get_status(self, project_cfg: ProjectConfig) -> ProjectStatus:
        required = [f.file_type for f in project_cfg.need_files if f.available]
        uploaded = [f.file_type for f in self.repository.list_files(project_cfg.project_id)]
        missing = [t for t in required if t not in uploaded]
        return ProjectStatus(
            project_id=project_cfg.project_id,
            required_types=required,
            uploaded_types=uploaded,
            missing_types=missing,
        )

    def list_files(self, project_id: str) -> list[StoredFile]:
        return self.repository.list_files(project_id)

    def delete_project_files(self, project_id: str) -> bool:
        return self.repository.delete_project(project_id)

    def _build_file_id(self, content_bytes: bytes) -> str:
        return hashlib.md5(content_bytes).hexdigest()

    def _build_response(
        self,
        project_id: str,
        file_id: str,
        filename: str,
        file_type: str,
        elements: dict[str, Any],
        content: str,
        cache_hit: bool,
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "file_id": file_id,
            "file_name": filename,
            "file_type": file_type,
            "elements": elements,
            "content_preview": content[:500],
            "cache_hit": cache_hit,
            "message": "文件上传并处理成功",
        }
