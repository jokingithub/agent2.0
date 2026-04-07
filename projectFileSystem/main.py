from __future__ import annotations

from pathlib import Path
from typing import Any, List
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import DEFAULT_LLM_CONFIG, DEFAULT_OCR_CONFIG, DEFAULT_PROJECT_ID, PROJECT_CONFIGS
from Schema import ProjectConfig, ProjectStatus, StoredFile
from services.content_extractor import ContentExtractor
from services.file_processor import FileProcessor, InMemoryProjectRepository
from services.project_config_repository import PgProjectConfigRepository
from services.stored_file_repository import PgStoredFileRepository
from services.storage import LocalFileStorage
from utils.errors import AppError, ConfigStoreError, ProjectNotFoundError, to_http_exception
from utils.logging import get_logger

UPLOAD_FOLDER = "uploadFiles"
_BASE_DIR = Path(__file__).resolve().parent
_UPLOAD_DIR = (_BASE_DIR / UPLOAD_FOLDER).resolve()
logger = get_logger(__name__)
app = FastAPI(title="配置驱动文件管理系统", version="1.0.0")
file_repository = InMemoryProjectRepository()
storage = LocalFileStorage(upload_dir=_UPLOAD_DIR)
extractor = ContentExtractor()
try:
    file_repository = PgStoredFileRepository()
    file_repository.ensure_schema()
except ConfigStoreError as exc:
    logger.warning("文件结果仓储未启用 PostgreSQL，回退到内存模式: %s", exc.detail)

processor = FileProcessor(storage=storage, extractor=extractor, repository=file_repository)
try:
    config_repo = PgProjectConfigRepository()
    config_repo.ensure_schema()
except ConfigStoreError as exc:
    config_repo = None
    logger.warning("PostgreSQL 未启用，回退到内存配置模式: %s", exc.detail)


class ProjectCreateRequest(BaseModel):
    need_files: list[dict[str, Any]]
    ocr: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None


def get_project_config(project_id: str) -> ProjectConfig:
    raw = config_repo.get_project(project_id) if config_repo else None
    if not raw:
        raw = PROJECT_CONFIGS.get(project_id)
    if not raw:
        raise ProjectNotFoundError(f"未找到项目配置: {project_id}")
    return ProjectConfig.model_validate(raw)


@app.exception_handler(AppError)
async def app_error_handler(_, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def save_file(file: Any, project_id: str = DEFAULT_PROJECT_ID) -> dict[str, Any]:
    content_bytes = await file.read()
    if hasattr(file, "seek"):
        await file.seek(0)
    project_cfg = get_project_config(project_id)
    return processor.process(project_cfg=project_cfg, filename=file.filename, content_bytes=content_bytes)


def get_project_status(project_id: str) -> ProjectStatus:
    cfg = get_project_config(project_id)
    return processor.get_status(cfg)


def list_project_files(project_id: str) -> List[StoredFile]:
    get_project_config(project_id)
    return processor.list_files(project_id)


def _generate_project_id() -> str:
    while True:
        project_id = f"proj_{uuid4().hex[:12]}"
        in_memory_exists = project_id in PROJECT_CONFIGS
        in_db_exists = bool(config_repo and config_repo.get_project(project_id))
        if not in_memory_exists and not in_db_exists:
            return project_id


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/projects")
def list_projects() -> dict[str, List[str]]:
    project_ids = config_repo.list_project_ids() if config_repo else []
    if not project_ids:
        project_ids = list(PROJECT_CONFIGS.keys())
    return {"project_ids": project_ids}


@app.post("/projects")
def create_project(payload: ProjectCreateRequest) -> dict[str, str]:
    project_id = _generate_project_id()
    if config_repo:
        config_repo.upsert_project(
            project_id=project_id,
            need_files=payload.need_files,
            ocr=payload.ocr or dict(DEFAULT_OCR_CONFIG),
            llm=payload.llm or dict(DEFAULT_LLM_CONFIG),
        )
    else:
        PROJECT_CONFIGS[project_id] = {
            "project_id": project_id,
            "need_files": payload.need_files,
            "ocr": payload.ocr or dict(DEFAULT_OCR_CONFIG),
            "llm": payload.llm or dict(DEFAULT_LLM_CONFIG),
        }
    get_project_config(project_id)
    return {"message": "项目创建成功", "project_id": project_id}


@app.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(status_code=400, detail="默认项目不允许删除")

    if config_repo:
        if not config_repo.get_project(project_id):
            raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
        if not config_repo.delete_project(project_id):
            raise ConfigStoreError(f"删除项目失败: {project_id}")
    else:
        if project_id not in PROJECT_CONFIGS:
            raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
        del PROJECT_CONFIGS[project_id]

    processor.delete_project_files(project_id)
    return {"message": "项目删除成功", "project_id": project_id}


@app.post("/projects/{project_id}/upload")
async def upload_file(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        return await save_file(file=file, project_id=project_id)
    except ProjectNotFoundError as e:
        raise to_http_exception(e)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.get("/projects/{project_id}/status")
def project_status(project_id: str) -> ProjectStatus:
    try:
        return get_project_status(project_id)
    except ProjectNotFoundError as e:
        raise to_http_exception(e)


@app.get("/projects/{project_id}/files")
def project_files(project_id: str) -> List[StoredFile]:
    try:
        return list_project_files(project_id)
    except ProjectNotFoundError as e:
        raise to_http_exception(e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)