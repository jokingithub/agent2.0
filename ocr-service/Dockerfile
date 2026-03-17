FROM python:3.10-slim

WORKDIR /app

# 复制OCR-service依赖
COPY ocr-service/requirements.txt ./ocr-requirements.txt
RUN pip install --no-cache-dir -r ocr-requirements.txt

# 复制主应用依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

EXPOSE 8001

CMD ["python", "ocr-service/main.py"]
