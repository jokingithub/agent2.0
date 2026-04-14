import requests
import os

# 配置你的 API Key
API_KEY = "sk-mFX7jrl9c4OPzpcdAiBzrCpaMjwUqKwceHLMcFHmpUR6LieW"
BASE_URL = "https://api.moonshot.cn/v1/files"

def process_moonshot_file(file_path):
    """
    完整流程：上传文件 -> 获取内容 -> 删除文件
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        # --- 1. 上传文件 ---
        print(f"正在上传文件: {file_path}...")
        with open(file_path, "rb") as f:
            upload_data = {
                "purpose": "file-extract" # 用于内容提取
            }
            files = {
                "file": (os.path.basename(file_path), f)
            }
            upload_res = requests.post(BASE_URL, headers=headers, files=files, data=upload_data)
            upload_res.raise_for_status() # 检查请求是否成功
            
        file_info = upload_res.json()
        file_id = file_info["id"]
        print(f"上传成功，文件 ID: {file_id}")

        # --- 2. 获取提取的文件内容 ---
        print("正在提取文件内容...")
        content_url = f"{BASE_URL}/{file_id}/content"
        content_res = requests.get(content_url, headers=headers)
        content_res.raise_for_status()
        
        extracted_text = content_res.text
        print("内容提取完成。")

        # --- 3. 删除文件 ---
        print(f"正在从服务器删除文件 {file_id}...")
        delete_url = f"{BASE_URL}/{file_id}"
        delete_res = requests.delete(delete_url, headers=headers)
        delete_res.raise_for_status()
        
        if delete_res.json().get("deleted"):
            print("文件删除成功。")
        
        return extracted_text

    except Exception as e:
        return f"处理过程中出错: {e}"

if __name__ == "__main__":
    # 替换为你本地的文件路径
    test_file = "/Users/niejing/work/AI2.0/test_data/bh.pdf" 
    
    # 如果文件不存在，创建一个简单的测试文件
    if not os.path.exists(test_file):
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("这是一个用于测试 Moonshot API 的示例文档内容。")

    # 执行流程
    result = process_moonshot_file(test_file)
    
    print("\n--- 最终提取结果 ---")
    print(result)