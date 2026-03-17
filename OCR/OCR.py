import os
import time
import logging
import numpy as np
import cv2
from PIL import Image
from typing import List, Tuple, Any, Generator, Optional
from concurrent.futures import ProcessPoolExecutor
from pdf2image import convert_from_path, pdfinfo_from_path

# 假设 paddle_OCR 是你自定义的包装类
# from paddle_OCR import paddle_OCR 

# --- 配置中心 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_SIDE_LIMIT = 2000
DEFAULT_DPI = 200  # 提高 DPI 以保证识别率
SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}

# --- 全局变量（仅在子进程中生效） ---
_ocr_instance = None

def get_ocr_instance(mode: str = "PP_OCRv5"):
    """子进程内单例模式获取 OCR 实例"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddle_OCR import paddle_OCR # 延迟加载
            _ocr_instance = paddle_OCR(mode=mode)
        except ImportError:
            logger.error("❌ 无法导入 paddle_OCR 模块")
            raise
    return _ocr_instance

def is_image(file_path: str) -> bool:
    """判断是否为常见图片格式"""
    return os.path.splitext(file_path)[1].lower() in SUPPORTED_IMAGE_EXTS

def process_batch_mp(args: Tuple[List[Any], List[Image.Image], str]) -> Optional[List[dict]]:
    """
    子进程执行的任务
    """
    batch_labels, images_pil, _ = args
    page_start = time.time()
    ocr = get_ocr_instance()
    
    try:
        # 1. 转换格式: PIL -> BGR NumPy
        imgs_bgr = []
        for img in images_pil:
            # 确保是 RGB 再转 BGR (处理灰度图或带透明通道的图)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img_np = np.array(img)
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            imgs_bgr.append(img_bgr)
        
        # 2. 调用批量预测
        # 假设 ocr.predict 返回的是一个可迭代的对象，每个元素支持 dict() 转换
        results = ocr.predict(image_path=imgs_bgr)
        
        # 3. 整理结果
        processed_results = []
        for label, res in zip(batch_labels, results):
            res_dict = dict(res)
            res_dict["source_label"] = label
            processed_results.append(res_dict)
        
        logger.info(f"✅ Batch {batch_labels} processed in {time.time() - page_start:.2f}s")
        return processed_results

    except Exception as e:
        logger.error(f"❌ Error in batch {batch_labels}: {str(e)}", exc_info=True)
        return None

def pdf_batch_generator(file_path: str, batch_size: int) -> Generator:
    """PDF 分页生成器"""
    try:
        info = pdfinfo_from_path(file_path)
        total_pages = info["Pages"]
        
        for i in range(1, total_pages + 1, batch_size):
            first_page = i
            last_page = min(i + batch_size - 1, total_pages)
            
            images = convert_from_path(
                file_path, 
                dpi=DEFAULT_DPI,
                first_page=first_page, 
                last_page=last_page,
                thread_count=4
            )
            labels = [f"page_{j}" for j in range(first_page, last_page + 1)]
            yield (labels, images, None)
    except Exception as e:
        logger.error(f"Failed to process PDF {file_path}: {e}")

def image_batch_generator(file_list: List[str], batch_size: int) -> Generator:
    """图片列表生成器：支持缩放和格式转换"""
    for i in range(0, len(file_list), batch_size):
        batch_files = file_list[i : i + batch_size]
        images = []
        labels = []
        
        for f in batch_files:
            try:
                with Image.open(f) as img:
                    # 获取当前尺寸并进行自适应缩放
                    w, h = img.size
                    max_side = max(w, h)
                    
                    if max_side > MAX_SIDE_LIMIT:
                        scale = MAX_SIDE_LIMIT / float(max_side)
                        new_size = (int(w * scale), int(h * scale))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # 转换并加载到内存
                    img = img.convert("RGB")
                    img.load() 
                    images.append(img)
                    labels.append(os.path.basename(f))
            except Exception as e:
                logger.warning(f"Skipping broken image {f}: {e}")
        
        if images:
            yield (labels, images, None)

def ocr_pipeline(input_path: str, workers: int = 1, batch_size: int = 4) -> List[dict]:
    """
    OCR 主流水线
    """
    if not os.path.exists(input_path):
        logger.error(f"Input path does not exist: {input_path}")
        return []

    # 1. 准备任务生成器
    if os.path.isdir(input_path):
        all_files = [os.path.join(input_path, f) for f in os.listdir(input_path)]
        image_files = sorted([f for f in all_files if is_image(f)])
        if not image_files:
            logger.warning("No valid images found in directory.")
            return []
        batch_gen = image_batch_generator(image_files, batch_size)
        logger.info(f"📂 Folder mode: {len(image_files)} images found.")

    elif os.path.isfile(input_path):
        if input_path.lower().endswith(".pdf"):
            batch_gen = pdf_batch_generator(input_path, batch_size)
            logger.info(f"📄 PDF mode: {input_path}")
        elif is_image(input_path):
            batch_gen = image_batch_generator([input_path], batch_size)
            logger.info(f"🖼️ Single image mode.")
        else:
            logger.error("Unsupported file format.")
            return []
    else:
        return []

    # 2. 并行执行
    total_results = []
    total_start = time.time()
    
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # map 会保持顺序
        future_results = executor.map(process_batch_mp, batch_gen)
        
        for res in future_results:
            if res:
                total_results.extend(res)

    logger.info(f"🏁 Task finished. Total time: {time.time() - total_start:.2f}s, Items: {len(total_results)}")
    return total_results

if __name__ == "__main__":
    # 使用建议：如果是 CPU 建议 workers = CPU核心数/2；如果是 GPU，通常 workers=1
    TARGET_PATH = "./test_data/1.png"
    
    if os.path.exists(TARGET_PATH):
        final_data = ocr_pipeline(
            input_path=TARGET_PATH,
            workers=1,
            batch_size=4
        )
        # print(final_data)
    else:
        logger.error("Please provide a valid path.")