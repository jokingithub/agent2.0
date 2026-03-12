import os,io
import mammoth
import pymupdf4llm
import pdfplumber
from charset_normalizer import from_path
from PIL import Image
# import pytesseract
from pdf2image import convert_from_path
from .baidu_ocr import BaiduOCR

# --- 配置区 ---
API_KEY = "GoBHYVgg4c1SMhcf0xYYqcWk"
SECRET_KEY = "lMC1VfOUx7XenpsIzLB6zZbB4YVn40FU"
# --------------

ocr_client = BaiduOCR(API_KEY, SECRET_KEY)

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
            full_ocr_text = []
            # 将 PDF 页面转为图片
            images = convert_from_path(path)
            for i, image in enumerate(images):
                # 将 PIL Image 对象转为 bytes
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG')
                image_bytes = img_byte_arr.getvalue()
                
                # 调用百度 OCR
                page_text = ocr_client.recognize(image_bytes)
                full_ocr_text.append(f"### Page {i+1}\n{page_text}")
            
            return "\n\n".join(full_ocr_text)
        
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
    """图片 OCR 占位逻辑"""
    # 以后开启 OCR 可以使用: 
    # return pytesseract.image_to_string(Image.open(path), lang='chi_sim+eng')
    return f"--- 图片内容: {os.path.basename(path)} (OCR 尚未启用) ---"