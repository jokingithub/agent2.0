import requests
import base64

class BaiduOCR:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        self.access_token = self._get_access_token()

    def _get_access_token(self):
        url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={self.api_key}&client_secret={self.secret_key}"
        res = requests.get(url)
        if res.status_code == 200:
            return res.json().get("access_token")
        raise Exception("百度 OCR Token 获取失败，请检查 Key")

    def recognize(self, image_bytes):
        # 使用高精度版 (general_enhanced)，对扭曲图片效果更好
        url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?access_token={self.access_token}"
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"image": img_base64}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        response = requests.post(url, data=payload, headers=headers)
        if response.status_code == 200:
            result = response.json()
            words = [item["words"] for item in result.get("words_result", [])]
            return "\n".join(words)
        return f"OCR 出错: {response.text}"