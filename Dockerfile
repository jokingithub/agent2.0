FROM python:3.10-slim

WORKDIR /app

# 升级pip
RUN pip install --upgrade pip

# 复制主应用依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
