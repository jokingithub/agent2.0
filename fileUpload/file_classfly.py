# -*- coding: utf-8 -*-
# 文件：fileUpload/file_classfly.py
# time: 2026/3/19

import re # 导入正则，用于更灵活的分隔
from app.core.llm import get_model
from logger import logger
from dataBase.ConfigService import FileProcessingService

# 保持在外面，避免重复加载模型
model = get_model(model_choice="high")

def classify_file(file_content: str) -> list[str]:
    """
    将文件内容分类，支持多分类返回
    """
    try:
        # 1. 从 file_processing 配置表读可用类型（单一来源）
        fp_configs = FileProcessingService().get_all()
        file_types = [
            str(c.get("file_type")).strip()
            for c in fp_configs
            if c.get("file_type") and str(c.get("file_type")).strip()
        ]
        # 去重，保持顺序
        file_types = list(dict.fromkeys(file_types))

        if not file_types:
            logger.warning("file_processing 表未配置 file_type，分类返回 ['其他']")
            return ["其他"]


        logger.info(f"当前可用文件类型: {file_types}")

        # 2. 构造更严谨的 Prompt
        types_str = "、".join(file_types)
        prompt = (
            f"你是一个文件分类专家。请分析以下内容，判断其属于以下哪些类别：[{types_str}]。\n"
            f"要求：\n"
            f"1. 只返回类别名称，不要包含任何解释、前缀或标点。\n"
            f"2. 如果属于多个类别，请用英文逗号(,)分隔。\n"
            f"3. 如果不属于任何已知类别，请返回'其他'。\n\n"
            f"文件内容：\n{file_content[:2000]}" # 限制长度防止超长
        )

        # 3. 调用模型
        response = model.invoke([("system", prompt)])
        classification_raw = response.content.strip()
        logger.debug(f"模型原始输出: {classification_raw}")

        # 4. 灵活解析结果
        # 使用正则表达式匹配中文逗号、英文逗号、顿号、空格等作为分隔符
        raw_list = re.split(r'[,，、\s\n]+', classification_raw)
        
        # 过滤：只保留在定义列表中的类型，并去重
        final_results = list(set([t for t in raw_list if t in file_types]))

        # 5. 兜底逻辑
        if not final_results:
            return ["其他"]
        
        return final_results

    except Exception as e:
        logger.error(f"分类过程发生异常: {e}", exc_info=True)
        return ["未知类型"] # 始终返回列表
