#!/bin/bash

# OCR服务独立conda环境设置脚本

set -e

echo "========================================="
echo "创建OCR服务独立conda环境"
echo "========================================="

# 配置变量
ENV_NAME="ocr-service"
PYTHON_VERSION="3.10"

# 检查conda是否安装
if ! command -v conda &> /dev/null; then
    echo "❌ conda未安装，请先安装Miniconda或Anaconda"
    exit 1
fi

# 检查环境是否已存在
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "⚠️  环境 $ENV_NAME 已存在"
    read -p "是否删除并重新创建? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "删除现有环境..."
        conda env remove -n "$ENV_NAME" -y
    else
        echo "使用现有环境，跳过创建步骤"
        exit 0
    fi
fi

# 创建新环境
echo "正在创建新环境: $ENV_NAME (Python $PYTHON_VERSION)"
conda create -n "$ENV_NAME" python="$PYTHON_VERSION" -y

# 激活环境
echo "激活环境..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

# 升级pip
echo "升级pip..."
pip install --upgrade pip

# 安装依赖
echo "安装依赖包..."
pip install -r requirements.txt

echo ""
echo "========================================="
echo "✅ OCR服务环境已成功创建！"
echo "========================================="
echo ""
echo "使用方法:"
echo "1. 激活环境: conda activate $ENV_NAME"
echo "2. 启动服务: python main.py"
echo "3. 服务地址: http://127.0.0.1:8001"
echo "4. API文档: http://127.0.0.1:8001/docs"
echo ""
echo "从主应用调用OCR服务:"
echo "在extract_content.py中使用以下代码:"
echo ""
echo "import httpx"
echo "async with httpx.AsyncClient() as client:"
echo "    response = await client.post("
echo '        "http://127.0.0.1:8001/ocr/process",'
echo "        json={'file_path': path, 'workers': 1, 'batch_size': 4}"
echo "    )"
echo ""
