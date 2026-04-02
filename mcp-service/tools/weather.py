from core.decorators import register_tool

@register_tool(category="weather")
def get_weather_local(city: str) -> str:
    """获取模拟天气。"""
    return f"{city}天气：晴，25℃"