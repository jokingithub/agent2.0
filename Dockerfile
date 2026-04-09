ARG BASE_IMAGE=python:3.10-slim-bookworm
FROM ${BASE_IMAGE}

WORKDIR /app

# 系统依赖（psycopg2、部分OCR依赖常见编译库）
RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential \
	libpq-dev \
  curl \
	&& rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# 使用 API 专用依赖（已剔除 OCR 冲突包）
COPY requirements-api.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
