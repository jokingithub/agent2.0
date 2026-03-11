from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser

def supervisor_node(state):
    members = ["Researcher", "Writer"]
    system_prompt = f"你是一个团队主管。根据任务进度选择执行者：{members}。如果任务已完成，请回复 FINISH。"
    
    # 这里的逻辑通常是利用 LLM 的 Function Calling 强制输出 JSON
    # 包含 {"next": "Researcher"} 这样的结构
    # ... (逻辑省略，核心是更新 state["next"])
    return {"next": "quotation"} # 示例中硬编码，实际应由 LLM 决定