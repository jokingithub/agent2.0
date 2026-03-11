from langchain_core.tools import tool

@tool
def calculate(expression: str) -> str:
    """计算表达式的值"""
    try:
        # 使用 eval 计算表达式的值
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"