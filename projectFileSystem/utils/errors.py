from __future__ import annotations

from fastapi import HTTPException


class AppError(Exception):
    """应用层基础异常。"""

    status_code = 500
    message = "服务内部错误"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.message
        super().__init__(self.detail)


class ProjectNotFoundError(AppError):
    status_code = 404
    message = "项目不存在"


class FileProcessError(AppError):
    status_code = 422
    message = "文件处理失败"


class ConfigStoreError(AppError):
    status_code = 500
    message = "配置存储异常"


def to_http_exception(err: AppError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=err.detail)
