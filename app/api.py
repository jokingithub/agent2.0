from typing import Any
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.graph.builder import create_graph

try:
    from langfuse.langchain import CallbackHandler
except Exception:
    CallbackHandler = None


app = FastAPI(title="AI2.0 API", version="1.0.0")
graph = create_graph()


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入")
    recursion_limit: int = Field(50, ge=1, le=200)


class ChatResponse(BaseModel):
    session_id: str
    final_message: str
    events: list[dict[str, Any]]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    callbacks = []
    if CallbackHandler is not None:
        callbacks.append(CallbackHandler())

    inputs = {
        "session_id": req.session_id,
        "messages": [("user", req.message)],
    }

    events: list[dict[str, Any]] = []
    final_message = ""

    async for output in graph.astream(
        inputs,
        config={
            "recursion_limit": req.recursion_limit,
            "configurable": {"thread_id": req.session_id},
            "callbacks": callbacks,
        },
    ):
        for node_name, node_value in output.items():
            event: dict[str, Any] = {"node": node_name}
            messages = node_value.get("messages") if isinstance(node_value, dict) else None
            if messages:
                last = messages[-1]
                content = getattr(last, "content", "")
                event["message"] = content
                if isinstance(content, str) and content.strip():
                    final_message = content
            events.append(event)

    return ChatResponse(
        session_id=req.session_id,
        final_message=final_message,
        events=events,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    callbacks = []
    if CallbackHandler is not None:
        callbacks.append(CallbackHandler())

    inputs = {
        "session_id": req.session_id,
        "messages": [("user", req.message)],
    }

    async def event_gen():
        final_message = ""

        async for output in graph.astream(
            inputs,
            config={
                "recursion_limit": req.recursion_limit,
                "configurable": {"thread_id": req.session_id},
                "callbacks": callbacks,
            },
        ):
            for node_name, node_value in output.items():
                payload: dict[str, Any] = {"node": node_name}
                messages = node_value.get("messages") if isinstance(node_value, dict) else None
                if messages:
                    last = messages[-1]
                    content = getattr(last, "content", "")
                    payload["message"] = content
                    if isinstance(content, str) and content.strip():
                        final_message = content

                yield f"event: node\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        done_payload = {
            "session_id": req.session_id,
            "final_message": final_message,
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
