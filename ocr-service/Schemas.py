from pydantic import BaseModel
from typing import List, Optional, Any

class OCRRequest(BaseModel):
    file_path: str
    batch_size: int = 4

class OCRResponse(BaseModel):
    success: bool
    data: Optional[List[Any]] = None
    error: Optional[str] = None