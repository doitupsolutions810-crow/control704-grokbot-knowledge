"""ChatBot Avrone Due'Krey chat + SSE stream."""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import db
from app import orchestrator
from app.config import get_settings
from app.llm import get_llm_provider
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])

SYSTEM_PROMPT = (
    "You are ChatBot Avrone Due'Krey, the operator console for Sub-Agent Orchestration "
    "and Spawn-Agent for Tasks. Be concise, ops-oriented, and actionable."
)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    settings = get_settings()
    if not settings.feature_chat:
        raise HTTPException(status_code=403, detail="chat feature disabled")

    job_id = body.job_id
    if job_id and not db.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in body.history[-20:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": body.message})

    provider = get_llm_provider()
    gated = not settings.allow_agent_execution

    if body.stream:
        # Non-stream path still available; clients wanting SSE use /chat/stream
        pass

    try:
        reply = await provider.chat(messages, model=body.model or settings.llm_model)
    except Exception as exc:
        if gated:
            reply = (
                f"[gated · mock] Avrone Due'Krey received: {body.message[:200]!r}. "
                f"Enable ALLOW_AGENT_EXECUTION and LiteLLM to run live models. ({exc})"
            )
        else:
            raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

    if job_id:
        db.insert_event(
            job_id,
            "chat.message",
            {"user": body.message[:2000], "reply_preview": reply[:500]},
        )

    return ChatResponse(
        reply=reply,
        job_id=job_id,
        model=body.model or settings.llm_model,
        gated=gated,
        meta={"product": "ChatBot Avrone Due'Krey"},
    )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    settings = get_settings()
    if not settings.feature_chat:
        raise HTTPException(status_code=403, detail="chat feature disabled")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in body.history[-20:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": body.message})

    provider = get_llm_provider()
    model = body.model or settings.llm_model

    async def event_gen() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'type': 'start', 'model': model})}\n\n"
        try:
            async for chunk in provider.stream_chat(messages, model=model):
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
