from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ElementSpec(BaseModel):
    """要抽取的要素定义。"""

    element_key: str = Field(..., description="要素字段名")
    description: str = Field(..., description="要素说明")


class FileTypeConfig(BaseModel):
    """文件类型配置。"""

    file_type: str = Field(..., description="文件类型名称")
    available: bool = Field(True, description="是否启用")
    aliases: List[str] = Field(default_factory=list, description="文件类型别名/关键字")
    elements: List[ElementSpec] = Field(default_factory=list, description="该类型要抽取的要素")


class OCRConfig(BaseModel):
    """OCR模型配置。"""

    provider: str = Field("remote_api", description="OCR提供方：remote_api/local")
    model_name: str = Field("default-ocr", description="OCR模型名称")
    endpoint: Optional[str] = Field(None, description="远程OCR接口地址")
    api_key: Optional[str] = Field(None, description="远程OCR密钥")
    timeout: int = Field(120, description="OCR超时秒数")


class LLMConfig(BaseModel):
    """LLM配置。"""

    model: str = Field("gpt-4o-mini", description="模型名称")
    api_key: Optional[str] = Field(None, description="API密钥")
    base_url: Optional[str] = Field(None, description="API基础地址")
    temperature: float = Field(0, description="采样温度")
    timeout: int = Field(120, description="请求超时秒数")


class ProjectConfig(BaseModel):
    """项目级配置。"""

    project_id: str = Field(..., description="项目ID")
    need_files: List[FileTypeConfig] = Field(default_factory=list, description="该项目需要的文件列表")
    ocr: OCRConfig = Field(default_factory=OCRConfig, description="该项目OCR配置")
    llm: LLMConfig = Field(default_factory=LLMConfig, description="该项目LLM配置")


class StoredFile(BaseModel):
    """已上传文件记录。"""

    file_id: str
    project_id: str
    original_name: str
    stored_path: str
    file_type: str
    content: str
    elements: Dict[str, Any] = Field(default_factory=dict)
    upload_time: datetime = Field(default_factory=datetime.now)


class ProjectStatus(BaseModel):
    """项目文件完成度状态。"""

    project_id: str
    required_types: List[str]
    uploaded_types: List[str]
    missing_types: List[str]