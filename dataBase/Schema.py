from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class FileModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(alias="_id", default=None)
    file_id: str
    file_name: str
    file_type: list[str]
    content: str

class MemoryModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(alias="_id", default=None)
    session_id: str
    timestamp: str
    role: str
    content: str

class FileTypeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(alias="_id", default=None)
    file_type: list[str]