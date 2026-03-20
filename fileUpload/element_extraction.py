# -*- coding: utf-8 -*-
import re
from app.core.llm import get_model
from logger import logger
from fileUpload.Schema import Letter_Of_Guarantee_Format
from prompt.file_prompt import system_prompt

model = get_model(model_choice="high").with_structured_output(Letter_Of_Guarantee_Format)

def element_extraction(file_content: str, file_type: str) -> dict:
    logger.info(f"正在处理文件类型: {file_type}")
    
    try:
        if "保函" in file_type:
            # 1. 构造清晰的消息结构
            messages = [
                ("system", system_prompt.ELEMENT_EXTRACTION_Letter_Of_Guarantee_Format),
                ("user", f"请从以下文本中提取要素：\n\n{file_content}")
            ]
            
            # 2. 调用模型
            # 注意：使用 with_structured_output 后，response 直接就是 Letter_Of_Guarantee_Format 对象
            response = model.invoke(messages)
            
            # 3. 记录并转换
            logger.debug(f"模型结构化输出: {response}")
            
            # 如果 response 是 Pydantic 模型，转为字典返回
            return response.dict() if hasattr(response, 'dict') else response

        else:
            logger.warning(f"{file_type} 未知类型，跳过提取")
            return {"error": "未知类型"}

    except Exception as e:
        logger.error(f"提取要素发生异常: {e}", exc_info=True)
        # 建议返回空字典或标准错误结构，而不是列表，保持返回类型一致
        return {"status": "error", "message": str(e)}