# -*- coding: utf-8 -*-
# 文件：fileUpload/extract_content.py
# time: 2026/3/18

import os
import requests
import mammoth
import logging
from charset_normalizer import from_path
from config import Config
from logger import logger

# 配置
OCR_SERVICE_URL = os.getenv(
    "OCR_SERVICE_URL",
    getattr(Config, "OCR_SERVICE_URL", "http://127.0.0.1:8001"),
)

def _format_ocr_to_markdown(ocr_results):
    """关键步骤：将 OCR 返回的数组拼接为可读文本"""
    if not ocr_results:
        return "[OCR 未识别到文字内容]"
    
    formatted_pages = []
    for page in ocr_results:
        idx = page.get("page_index", "?")
        # 提取 rec_texts 数组
        lines = page.get("rec_texts", [])
        # 过滤空行并拼接
        clean_text = "\n".join([line.strip() for line in lines if line.strip()])
        
        # 格式化输出
        formatted_pages.append(f"### 第 {idx} 页\n\n{clean_text}")
    
    return "\n\n---\n\n".join(formatted_pages)

def _call_ocr_api(file_path):
    """请求远程 OCR 服务。

    说明：当 OCR 服务在外部机器/容器外运行时，传 file_path 会指向本机临时路径，
    远端无法访问。因此这里统一走文件上传接口 /ocr/file。
    """
    try:
        with open(file_path, "rb") as f:
            files = {
                "file": (
                    os.path.basename(file_path),
                    f,
                    "application/octet-stream",
                )
            }
            data = {"batch_size": 4}
            resp = requests.post(
                f"{OCR_SERVICE_URL}/ocr/file",
                files=files,
                data=data,
                timeout=300,
            )

        if resp.status_code == 200 and resp.json().get("success"):
            return resp.json().get("data")

        logger.error(
            "OCR API 非成功响应: status=%s body=%s",
            resp.status_code,
            resp.text[:1000],
        )
        return None
    except Exception as e:
        logger.error(f"OCR API Error: {e}")
        return None

def extract_content(file_path):
    """主入口"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext in ['.doc', '.docx', '.rtf', '.excel']:
            with open(file_path, "rb") as f:
                return mammoth.convert_to_markdown(f).value
                
        elif ext == '.pdf':
            # 这里演示直接进入 OCR 逻辑（针对扫描件）
            logger.info(f"正在识别 PDF: {file_path}...")
            results = _call_ocr_api(file_path)
            return _format_ocr_to_markdown(results)
            
        elif ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            logger.info(f"正在识别图片: {file_path}...")
            results = _call_ocr_api(file_path)
            return _format_ocr_to_markdown(results)
            
        elif ext in ['.txt', '.md']:
            res = from_path(file_path).best()
            return str(res) if res else "读取失败"
    except Exception as e:
        logger.error(f"提取内容失败: {e}")
        return f"提取内容失败: {str(e)}"

if __name__ == "__main__":
    # 测试
    test_file = "test.pdf" 
    if os.path.exists(test_file):
        md_result = extract_content(test_file)
        print("\n--- 提取结果 ---\n")
        print(md_result)