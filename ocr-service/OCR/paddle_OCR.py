# -*- coding: utf-8 -*-
# 文件：ocr-service/OCR/paddle_OCR.py
# time: 2026/3/17

from paddleocr import PaddleOCR, PPStructureV3

class paddle_OCR():
    def __init__(self, mode="PP_OCRv5"):
        if mode == "PP_OCRv5":
            self.ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False
            )
        
        elif mode == "PPStructureV3":
            self.ocr = PPStructureV3(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False
            )


    def predict(self, image_path):
        if image_path is not None:
            try:
                return self.ocr.predict(input=image_path)
            except Exception as e:
                print(f"Error occurred while predicting: {e}")
                return None
