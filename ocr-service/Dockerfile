ARG BASE_IMAGE=m.daocloud.io/docker.io/library/python:3.10-slim
FROM ${BASE_IMAGE}

WORKDIR /app

# OCR 运行常见系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
	libgl1 \
	libglib2.0-0 \
	&& rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# 仅安装 OCR 环境导出的依赖
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . /app

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
