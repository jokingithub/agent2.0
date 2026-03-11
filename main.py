from app.graph.builder import create_graph

if __name__ == "__main__":
    app = create_graph()
    
    inputs = {
        "messages": [("user", "一般格式、金额12万，期限6个月，请计算报价。报价单路径：/Users/niejing/work/AI2.0/workspace/quotation.md")],
    }
    # inputs = {
    #     "messages": [("user", "1+1=几？")],
    # }
    
    for output in app.stream(inputs, config={"recursion_limit": 50}):
        # 打印各阶段的输出
        for key, value in output.items():
            print(f"Node '{key}' is active.")

            # 打印该节点返回的消息（如果有）
            messages = value.get("messages") if isinstance(value, dict) else None
            if messages:
                last = messages[-1]
                content = getattr(last, "content", str(last))
                print(f"Node '{key}' message: {content}")