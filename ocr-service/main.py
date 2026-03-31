# -*- coding: utf-8 -*-
# 文件：ocr-service/main.py

import sys
import os
import multiprocessing
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Any
import numpy as np
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException
# 导入 CORS 中间件
from fastapi.middleware.cors import CORSMiddleware

from Schemas import OCRRequest, OCRResponse
from OCR.OCR import ocr_pipeline_with_executor

# --- 环境配置 ---
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
os.environ['OMP_NUM_THREADS'] = '1'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 全局进程池变量 ---
ocr_executor: Optional[ProcessPoolExecutor] = None

# --- 数据清理工具 ---
def convert_to_native(data: Any) -> Any:
    BLACKLIST = ('font', 'input', 'doc_preprocessor_res', 'vis_fonts', 'model_settings',
                 'dt_polys', 'rec_scores', 'rec_polys', 'textline_orientation_angles', 'rec_boxes')
    if isinstance(data, dict):
        return {k: convert_to_native(v) for k, v in data.items() if k not in BLACKLIST}
    elif isinstance(data, list):
        return [convert_to_native(i) for i in data]
    elif isinstance(data, np.ndarray):
        return data.tolist()
    elif isinstance(data, np.generic):
        return data.item()
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    else:
        return str(data)

# --- FastAPI 生命周期管理 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_executor
    max_workers = 2
    logger.info(f"正在初始化常驻 OCR 进程池 (Workers: {max_workers})...")
    ocr_executor = ProcessPoolExecutor(max_workers=max_workers)
    yield
    if ocr_executor:
        ocr_executor.shutdown(wait=True)
        logger.info("OCR 进程池已安全关闭")

app = FastAPI(title="OCR Service", lifespan=lifespan)

# --- 新增：CORS 配置 ---
# 允许访问的源列表
# 在生产环境下，建议将 ["*"] 替换为具体的域名，例如 ["http://localhost:3000", "https://yourdomain.com"]
origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # 允许跨域请求的域名列表
    allow_credentials=True,          # 允许携带 Cookie
    allow_methods=["*"],             # 允许的 HTTP 方法 (GET, POST, OPTIONS 等)
    allow_headers=["*"],             # 允许的 HTTP 请求头
)

@app.get("/health")
async def health() -> dict:
    available = ocr_executor is not None
    return {
        "status": "ok" if available else "not_ready",
        "ocr_available": available,
    }

@app.post("/ocr/process", response_model=OCRResponse)
async def process_ocr(request: OCRRequest):
    try:
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {request.file_path}")
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, 
            ocr_pipeline_with_executor, 
            request.file_path, 
            ocr_executor, 
            request.batch_size
        )
        
        return OCRResponse(success=True, data=convert_to_native(results))
    except Exception as e:
        logger.error(f"OCR失败: {str(e)}", exc_info=True)
        return OCRResponse(success=False, error=str(e))

@app.post("/ocr/file")
async def process_ocr_file(file: UploadFile = File(...), batch_size: int = 4):
    try:
        temp_dir = Path("/tmp/ocr_uploads")
        temp_dir.mkdir(exist_ok=True)
        file_path = temp_dir / file.filename
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, 
            ocr_pipeline_with_executor, 
            str(file_path), 
            ocr_executor, 
            batch_size
        )
        
        return {"success": True, "filename": file.filename, "data": convert_to_native(results)}
    except Exception as e:
        logger.error(f"上传文件OCR失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    if sys.platform != 'linux':
        try:
            multiprocessing.set_start_method('spawn', force=True)
        except RuntimeError:
            pass

    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)