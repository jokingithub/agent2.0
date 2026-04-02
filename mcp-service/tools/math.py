from core.decorators import register_tool

@register_tool(category="math")
def calculate(expression: str) -> str:
    """执行数学运算。"""
    try:
        return f"结果: {eval(expression, {'__builtins__': {}})}"
    except:
        return "计算错误"