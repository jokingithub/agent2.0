# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from fileUpload.Schema import Letter_Of_Guarantee_Format

class FileModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    file_id: str                   # 业务唯一ID
    file_name: str
    file_type: List[str]
    content: str
    main_info: Optional[Letter_Of_Guarantee_Format] = None
    upload_time: datetime = Field(default_factory=datetime.now)

class MemoryModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[Any] = Field(alias="_id", default=None)
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    role: str                      # 'user' or 'assistant'
    content: str

class FileTypeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_type: List[str]

class SessionModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    file_list: List[str] = Field(default_factory=list) # 存储 file_id (string)