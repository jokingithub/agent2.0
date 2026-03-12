import os
from fileUpload.extract_content import extract_content

def main(session_id="123"):
    # 1. 定义输出目录并确保它存在
    output_dir = f"./sessions/{session_id}"
    if not os.path.exists(output_dir):
        # os.makedirs 可以递归创建多级目录，exist_ok=True 防止并发创建时报错
        os.makedirs(output_dir, exist_ok=True)
        print(f"创建目录: {output_dir}")

    # 测试文件列表
    test_files = [
        "./test_data/bh.pdf"
    ]

    for file_path in test_files:
        if os.path.exists(file_path):
            print(f"正在处理: {file_path}")
            try:
                # 调用提取函数
                result = extract_content(file_path)
                
                # 2. 动态生成输出文件名（例如 test.docx -> test.md）
                base_name = os.path.basename(file_path)  # 获取 "test.docx"
                file_stem = os.path.splitext(base_name)[0] # 获取 "test"
                output_file = os.path.join(output_dir, f"{file_stem}.md")

                # 3. 写入文件
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(result)
                
                print(f"提取成功，已保存至: {output_file}")
                
            except Exception as e:
                print(f"处理 {file_path} 时出错: {e}")
        else:
            print(f"源文件未找到: {file_path}")

if __name__ == "__main__":
    main()