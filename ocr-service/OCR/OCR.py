# -*- coding: utf-8 -*-
# 文件：ocr-service/OCR/OCR.py
# time: 2026/3/17

import os
import time
import logging
import numpy as np
import cv2
from PIL import Image
from typing import List, Tuple, Any, Generator, Optional
from concurrent.futures import ProcessPoolExecutor
from pdf2image import convert_from_path, pdfinfo_from_path

# --- 配置中心 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_SIDE_LIMIT = 2000
DEFAULT_DPI = 100 
SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}

# --- 全局变量（仅在子进程中生效） ---
_ocr_instance = None

def get_ocr_instance(mode: str = "PP_OCRv5"):
    """子进程内单例模式获取 OCR 实例"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            # 延迟加载，防止主进程初始化导致的显存占用或多进程冲突
            from OCR.paddle_OCR import paddle_OCR 
            _ocr_instance = paddle_OCR(mode=mode)
            logger.info(f"🚀 [PID {os.getpid()}] OCR Model Loaded.")
        except ImportError:
            logger.error("❌ 无法导入 paddle_OCR 模块")
            raise
    return _ocr_instance

def is_image(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in SUPPORTED_IMAGE_EXTS

def process_batch_mp(args: Tuple[List[Any], List[Image.Image], str]) -> Optional[List[dict]]:
    """子进程执行的任务"""
    batch_labels, images_pil, _ = args
    page_start = time.time()
    
    # 这一步非常关键：如果模型没加载则加载，加载了则直接返回
    ocr = get_ocr_instance()
    
    try:
        imgs_bgr = []
        for img in images_pil:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img_np = np.array(img)
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            imgs_bgr.append(img_bgr)
        
        results = ocr.predict(image_path=imgs_bgr)
        
        processed_results = []
        for label, res in zip(batch_labels, results):
            res_dict = dict(res)
            res_dict["page_index"] = label
            processed_results.append(res_dict)
        
        logger.info(f"✅ Batch {batch_labels} processed in {time.time() - page_start:.2f}s")
        return processed_results
    except Exception as e:
        logger.error(f"❌ Error in batch {batch_labels}: {str(e)}", exc_info=True)
        return None

def get_batch_generator(input_path: str, batch_size: int):
    """根据路径类型返回对应的生成器"""
    if os.path.isdir(input_path):
        all_files = [os.path.join(input_path, f) for f in os.listdir(input_path)]
        image_files = sorted([f for f in all_files if is_image(f)])
        return image_batch_generator(image_files, batch_size) if image_files else None
    
    elif os.path.isfile(input_path):
        if input_path.lower().endswith(".pdf"):
            return pdf_batch_generator(input_path, batch_size)
        elif is_image(input_path):
            return image_batch_generator([input_path], batch_size)
    return None

def pdf_batch_generator(file_path: str, batch_size: int) -> Generator:
    try:
        info = pdfinfo_from_path(file_path)
        total_pages = info["Pages"]
        for i in range(1, total_pages + 1, batch_size):
            first_page, last_page = i, min(i + batch_size - 1, total_pages)
            images = convert_from_path(file_path, dpi=DEFAULT_DPI, first_page=first_page, last_page=last_page)
            labels = [j for j in range(first_page, last_page + 1)]
            yield (labels, images, None)
    except Exception as e:
        logger.error(f"Failed to process PDF {file_path}: {e}")

def image_batch_generator(file_list: List[str], batch_size: int) -> Generator:
    for i in range(0, len(file_list), batch_size):
        batch_files = file_list[i : i + batch_size]
        images, labels = [], []
        for f in batch_files:
            try:
                with Image.open(f) as img:
                    w, h = img.size
                    max_side = max(w, h)
                    if max_side > MAX_SIDE_LIMIT:
                        scale = MAX_SIDE_LIMIT / float(max_side)
                        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                    img = img.convert("RGB")
                    img.load() 
                    images.append(img)
                    labels.append(os.path.basename(f))
            except Exception as e:
                logger.warning(f"Skipping broken image {f}: {e}")
        if images:
            yield (labels, images, None)

def ocr_pipeline_with_executor(input_path: str, executor: ProcessPoolExecutor, batch_size: int = 4) -> List[dict]:
    """核心流水线：使用传入的进程池执行"""
    batch_gen = get_batch_generator(input_path, batch_size)
    if not batch_gen:
        return []

    total_results = []
    # 使用 executor.map 提交任务，此时子进程会复用已加载的模型
    future_results = executor.map(process_batch_mp, batch_gen)
    
    for res in future_results:
        if res:
            total_results.extend(res)
    return total_results