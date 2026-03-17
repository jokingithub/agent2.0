import os,io
import mammoth
import pymupdf4llm
import pdfplumber
from charset_normalizer import from_path
from PIL import Image
# import pytesseract
from pdf2image import convert_from_path
from pathlib import Path
import logging


# OCR 配置
USE_OCR_SERVICE = True  # 是否使用独立的OCR服务（推荐生产环境使用）
OCR_SERVICE_URL = "http://127.0.0.1:8001"  # OCR服务地址

# 设置日志
logger = logging.getLogger(__name__)

# 根据配置导入OCR模块或设置HTTP客户端
if not USE_OCR_SERVICE:
    print("使用本地OCR模式")   # 本地OCR模式，直接导入OCR管道
else:
    # 远程OCR服务模式
    try:
        import requests
    except ImportError:
        logger.warning("requests库未安装，请运行: pip install requests")
        requests = None

# 可选：如果需要使用百度OCR作为备选，保留下面的代码
# from .baidu_ocr import BaiduOCR
# ocr_client = BaiduOCR(API_KEY, SECRET_KEY)

def extract_content(file_path):
    """
    根据文件后缀名提取内容，并尽可能转换为 Markdown 格式
    """
    if not os.path.exists(file_path):
        return f"文件不存在: {file_path}"
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.docx':
        return _extract_docx_to_markdown(file_path)
    elif ext == '.pdf':
        return _extract_pdf_to_markdown(file_path)
    elif ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
        return _extract_image(file_path)
    elif ext in ['.txt', '.md', '.py', '.js', '.json']:
        return _extract_txt_to_markdown(file_path)
    else:
        return f"不支持的文件类型: {ext}"

def _call_ocr_pipeline(file_path, workers=1, batch_size=4):
    """
    调用OCR处理：支持本地和远程服务两种模式
    
    Args:
        file_path: 文件路径（支持相对或绝对路径）
        workers: 工作进程数（本地模式使用）
        batch_size: 批处理大小（本地模式使用）
    
    Returns:
        OCR结果列表或None
    """
    # 转换为绝对路径（支持远程服务调用）
    abs_file_path = os.path.abspath(file_path)
    
    if not USE_OCR_SERVICE:
        # 本地OCR模式
        print(f"使用本地OCR处理: {abs_file_path}")
    else:
        # 远程OCR服务模式
        if requests is None:
            logger.error("requests库未安装，无法调用远程OCR服务")
            return None
        
        try:
            response = requests.post(
                f"{OCR_SERVICE_URL}/ocr/process",
                json={
                    "file_path": abs_file_path,
                    "workers": workers,
                    "batch_size": batch_size
                },
                timeout=300  # 5分钟超时
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return result.get("data")
                else:
                    logger.error(f"OCR服务返回错误: {result.get('error')}")
                    return None
            else:
                logger.error(f"OCR服务请求失败: {response.status_code}")
                return None
        except requests.exceptions.ConnectionError:
            logger.error(f"无法连接到OCR服务: {OCR_SERVICE_URL}")
            return None
        except Exception as e:
            logger.error(f"调用OCR服务失败: {e}")
            return None

def _extract_docx_to_markdown(path):
    """docx 转 Markdown"""
    try:
        with open(path, "rb") as docx_file:
            # mammoth 能够识别表格、标题、列表
            result = mammoth.convert_to_markdown(docx_file)
            return result.value
    except Exception as e:
        return f"docx 转换失败: {str(e)}"

def _extract_pdf_to_markdown(path):
    """PDF 提取：文字版直接转，图片版调用 OCR"""
    try:
        # 1. 尝试提取文字版 Markdown
        # md_text = pymupdf4llm.to_markdown(path)
        md_text = ""
        
        # 2. 如果字数太少，说明是扫描件，启动 OCR
        if len(md_text.strip()) < 20:
            print(f"检测到扫描版 PDF: {path}，正在执行 OCR...")
            
            try:
                # 使用 OCR 流水线处理 PDF（本地或远程）
                ocr_results = _call_ocr_pipeline(
                    file_path=path,
                    workers=1,  # 单进程模式便于集成
                    batch_size=1
                )
                
                if ocr_results:
                    # 整理 OCR 结果为 Markdown 格式
                    full_ocr_text = []
                    for result in ocr_results:
                        page_label = result.get("source_label", "unknown") if isinstance(result, dict) else "unknown"
                        # result 中包含 OCR 结果数据
                        full_ocr_text.append(f"### {page_label}\n{result}")
                    
                    return "\n\n".join(full_ocr_text)
                else:
                    return "[PDF 包含图片内容，但 OCR 处理失败]\n无法自动识别文本内容，建议手动查看原文件。"
            
            except Exception as ocr_error:
                print(f"⚠️ OCR 处理失败: {ocr_error}，返回占位符内容...")
                return f"[PDF 包含图片内容，但 OCR 处理失败: {str(ocr_error)[:100]}...]\n无法自动识别文本内容，建议手动查看原文件。"
        
        return md_text
    except Exception as e:
        return f"PDF 处理出错: {e}"

def _extract_txt_to_markdown(path):
    """
    文本文件读取：自动检测编码并清洗格式。
    在 Markdown 语境下，通常保持原样即可。
    """
    try:
        # 使用 charset-normalizer 自动检测并读取编码（解决 utf-8/gbk 冲突）
        results = from_path(path)
        best_guess = results.best()
        
        if best_guess:
            content = str(best_guess)
            # 基础清洗：移除行尾空格，确保 Markdown 渲染整齐
            lines = [line.rstrip() for line in content.splitlines()]
            return "\n".join(lines)
        else:
            return "无法识别该文本文件的编码格式。"
    except Exception as e:
        return f"TXT 读取失败: {str(e)}"

def _extract_image(path):
    """使用 OCR 流水线提取图片文字（本地或远程）"""
    try:
        print(f"正在对图片进行 OCR: {os.path.basename(path)}...")
        
        # 使用 OCR 流水线处理图片（本地或远程）
        ocr_results = _call_ocr_pipeline(
            file_path=path,
            workers=1,
            batch_size=1
        )
        
        if ocr_results:
            # 提取文字内容
            return str(ocr_results[0])
        else:
            return f"未能识别图片内容: {os.path.basename(path)}"
    except Exception as e:
        return f"图片 OCR 处理失败: {str(e)}"