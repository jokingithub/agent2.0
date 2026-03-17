# OCR 独立服务

这是一个基于 FastAPI 的独立 OCR 服务，使用 PaddleOCR 引擎进行文字识别。该服务运行在独立的 conda 环境中，与主应用程序解耦。

## 特点

- 🎯 独立的OCR微服务架构
- 🔄 支持多种文件格式（图片、PDF等）
- ⚡ 使用PaddleOCR引擎，识别率高
- 🌐 提供RESTful API接口
- 📚 自动生成的API文档（Swagger UI）

## 环境设置

### 1. 创建独立的conda环境

```bash
cd ocr-service
chmod +x setup.sh
./setup.sh
```

或手动创建：

```bash
# 创建环境
conda create -n ocr-service python=3.10 -y

# 激活环境
conda activate ocr-service

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动OCR服务

```bash
# 确保激活了ocr-service环境
conda activate ocr-service

# 启动服务
python main.py
```

服务将运行在 `http://127.0.0.1:8001`

## API 使用

### 1. 健康检查

```bash
curl http://127.0.0.1:8001/health
```

### 2. 处理本地文件

**请求：**
```bash
curl -X POST "http://127.0.0.1:8001/ocr/process" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/path/to/file.pdf",
    "workers": 1,
    "batch_size": 4
  }'
```

**响应：**
```json
{
  "success": true,
  "data": [
    {
      "page": 0,
      "text": "识别出的文字...",
      ...
    }
  ],
  "error": null
}
```

### 3. 上传文件进行识别

```bash
curl -X POST "http://127.0.0.1:8001/ocr/file" \
  -F "file=@/path/to/image.jpg"
```

## 与主应用集成

在主应用中调用OCR服务：

```python
import httpx
from pathlib import Path

async def extract_image_with_ocr(file_path: str) -> str:
    """通过OCR服务识别图片文字"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:8001/ocr/process",
                json={
                    "file_path": file_path,
                    "workers": 1,
                    "batch_size": 4
                },
                timeout=300.0  # 30秒超时
            )
            
            if response.status_code == 200:
                result = response.json()
                if result["success"]:
                    # 处理识别结果
                    return result["data"]
                else:
                    raise Exception(f"OCR failed: {result['error']}")
            else:
                raise Exception(f"OCR service error: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to call OCR service: {e}")
        raise
```

或同步方式：

```python
import requests

def extract_image_with_ocr(file_path: str) -> str:
    """通过OCR服务识别图片文字"""
    try:
        response = requests.post(
            "http://127.0.0.1:8001/ocr/process",
            json={
                "file_path": file_path,
                "workers": 1,
                "batch_size": 4
            },
            timeout=300
        )
        
        if response.status_code == 200:
            result = response.json()
            if result["success"]:
                return result["data"]
            else:
                raise Exception(f"OCR failed: {result['error']}")
        else:
            raise Exception(f"OCR service error: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to call OCR service: {e}")
        raise
```

## 生产部署

### Docker部署

可选地创建 `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["python", "main.py"]
```

构建和运行：

```bash
docker build -t ocr-service:1.0 .
docker run -p 8001:8001 ocr-service:1.0
```

### 使用systemd服务（Linux）

创建 `/etc/systemd/system/ocr-service.service`:

```ini
[Unit]
Description=OCR Service
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/ocr-service
ExecStart=/opt/conda/envs/ocr-service/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ocr-service
sudo systemctl start ocr-service
```

## 常见问题

### 1. PaddleOCR下载模型时很慢

PaddleOCR 首次运行时会下载预训练模型。可以提前下载：

```python
from paddleocr import PaddleOCR

# 预加载
ocr = PaddleOCR(use_angle_cls=True, lang='ch')
```

### 2. 内存占用过高

可以调整批处理大小和并发工作进程数：

```json
{
  "file_path": "/path/to/file",
  "workers": 1,
  "batch_size": 2
}
```

### 3. 识别效果不理想

- 确保图片清晰度足够
- 适当增加DPI（在OCR.py中调整 DEFAULT_DPI）
- 使用 `PPStructureV3` 模式处理复杂排版

## 架构图

```
┌─────────────────────────┐
│   Main Application      │
│  (extract_content.py)   │
└────────────┬────────────┘
             │ HTTP Request
             ▼
┌─────────────────────────┐
│   OCR Service           │
│  (FastAPI + Uvicorn)    │
│  [ocr-service conda]    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│   PaddleOCR Engine      │
│   (paddle_OCR.py)       │
└─────────────────────────┘
```

## 环境管理

### 列出所有conda环境

```bash
conda env list
```

### 删除ocr-service环境

```bash
conda env remove -n ocr-service
```

### 导出环境配置

```bash
# 从ocr-service环境导出
conda activate ocr-service
conda env export > ocr-service-env.yml

# 从配置重建环境
conda env create -f ocr-service-env.yml
```

## 性能优化建议

1. **增加工作进程数**：如果CPU充足，增加 `workers` 参数
2. **调整批大小**：根据GPU/CPU内存调整 `batch_size`
3. **缓存模型**：首次运行后，模型会被缓存，后续启动更快
4. **使用GPU**：如果有CUDA支持的GPU，PaddleOCR会自动使用

## 许可

与主应用程序相同
