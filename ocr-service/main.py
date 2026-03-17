import sys
import os
import multiprocessing
import logging
from pathlib import Path
from typing import List, Optional, Any

# --- 1. 环境配置 (必须在导入 paddle 相关包之前) ---
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
import uvicorn
import numpy as np

# 导入 OCR 逻辑
from OCR.OCR import ocr_pipeline

# --- 2. 日志配置 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 3. 工具函数：处理 Numpy 类型序列化并过滤无用字段 ---
def convert_to_native(data: Any) -> Any:
    """
    递归转换并过滤：
    - 过滤键: 'font', 'input', 'doc_preprocessor_res', 'vis_fonts'
    - 处理类型: numpy -> python native, 其他对象 -> str
    """
    # 定义不需要返回给前端的冗余或大体积字段
    BLACKLIST = (
        'font', 
        'input', 
        'doc_preprocessor_res',  # 包含预处理后的全量图片数组
        'vis_fonts',             # 包含可视化字体对象列表
        'model_settings',        # 包含模型配置元数据（可选过滤）
        'dt_polys',
        'rec_scores',
        'rec_polys',
        'textline_orientation_angles',
        'rec_boxes'





    )

    if isinstance(data, dict):
        return {
            k: convert_to_native(v) 
            for k, v in data.items() 
            if k not in BLACKLIST
        }
    
    elif isinstance(data, list):
        return [convert_to_native(i) for i in data]
    
    elif isinstance(data, np.ndarray):
        return data.tolist()
    
    elif isinstance(data, np.generic):
        return data.item()
    
    # 针对 paddlex 的特殊对象进行降级处理
    elif "paddlex" in str(type(data)):
        return None
    
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    
    else:
        return str(data)

# --- 4. FastAPI 应用声明 ---
app = FastAPI(
    title="OCR Service",
    description="独立的文本识别服务，使用PaddleOCR引擎",
    version="1.0.0"
)

class OCRRequest(BaseModel):
    file_path: str
    workers: int = 1
    batch_size: int = 4

class OCRResponse(BaseModel):
    success: bool
    data: Optional[List[Any]] = None
    error: Optional[str] = None

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "OCR Service"}

@app.post("/ocr/process", response_model=OCRResponse)
async def process_ocr(request: OCRRequest):
    try:
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {request.file_path}")
        
        results = ocr_pipeline(
            input_path=request.file_path,
            workers=request.workers,
            batch_size=request.batch_size
        )
        
        # 过滤并转换数据
        clean_results = convert_to_native(results)
        
        return OCRResponse(
            success=True,
            data=clean_results
        )
    except Exception as e:
        logger.error(f"OCR处理失败: {str(e)}", exc_info=True)
        return OCRResponse(success=False, error=str(e))

@app.post("/ocr/file")
async def process_ocr_file(
    file: UploadFile = File(...),
    workers: int = 1,
    batch_size: int = 4
):
    try:
        temp_dir = Path("/tmp/ocr_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / file.filename
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        results = ocr_pipeline(
            input_path=str(file_path),
            workers=workers,
            batch_size=batch_size
        )
        
        clean_results = convert_to_native(results)
        
        return {
            "success": True,
            "filename": file.filename,
            "data": clean_results
        }
    except Exception as e:
        logger.error(f"文件OCR处理失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OCR处理失败: {str(e)}")

# --- 5. 启动入口 ---
if __name__ == "__main__":
    if sys.platform == 'darwin':
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            pass

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        log_level="info",
        reload=False
    )