#!/usr/bin/env python3
"""
OpenAI-compatible vLLM protocol shim.

Real vLLM requires CUDA/GPU. When GPU/vLLM is unavailable this FastAPI app
exposes /v1/chat/completions and proxies to LiteLLM (or returns mock completions).

Enable real vLLM:
  1. nvidia-smi works
  2. pip install 'vllm' (see scripts/install_deps.sh)
  3. set AVRONE_USE_REAL_VLLM=1 and VLLM_MODEL=<hf model id>
  4. restart avrone-daemon — daemon will prefer real vLLM if configured
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="avrone-vllm-shim", version="1.0.0")
UPSTREAM = os.environ.get("VLLM_UPSTREAM", "http://127.0.0.1:4000/v1")
MODE = "shim"  # shim | real (informational)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "mock-gpt"
    messages: list[ChatMessage]
    temperature: float = 0.2
    stream: bool = False
    max_tokens: Optional[int] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "vllm-shim",
        "mode": MODE,
        "upstream": UPSTREAM,
        "gpu": False,
        "note": "Protocol-compatible shim; install real vLLM when CUDA is present",
    }


@app.get("/v1/models")
def models():
    return {
        "object": "list",
        "data": [
            {"id": "mock-gpt", "object": "model", "owned_by": "avrone"},
            {"id": "avrone-local", "object": "model", "owned_by": "avrone"},
        ],
    }


def _mock_completion(req: ChatRequest) -> dict[str, Any]:
    last = req.messages[-1].content if req.messages else ""
    text = (
        f"[vllm-shim→litellm unavailable] Echo from Avrone Due'Krey: {last[:400]}"
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    payload = req.model_dump()
    # Prefer upstream LiteLLM
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if req.stream:
                # For stream, try upstream; fall back to fake SSE
                try:
                    r = await client.post(
                        f"{UPSTREAM.rstrip('/')}/chat/completions",
                        json=payload,
                    )
                    if r.status_code < 400:
                        # Non-stream proxy for simplicity when upstream ignores stream
                        data = r.json()
                        content = data["choices"][0]["message"]["content"]

                        def gen():
                            yield f'data: {{"id":"chatcmpl-shim","object":"chat.completion.chunk","choices":[{{"delta":{{"content":{content!r}}}}}]}}\n\n'
                            yield "data: [DONE]\n\n"

                        return StreamingResponse(gen(), media_type="text/event-stream")
                except Exception:
                    pass

                text = _mock_completion(req)["choices"][0]["message"]["content"]

                def gen_mock():
                    yield (
                        'data: {"id":"chatcmpl-shim","object":"chat.completion.chunk",'
                        f'"choices":[{{"delta":{{"content":{text!r}}}}}]}}\n\n'
                    )
                    yield "data: [DONE]\n\n"

                return StreamingResponse(gen_mock(), media_type="text/event-stream")

            r = await client.post(
                f"{UPSTREAM.rstrip('/')}/chat/completions",
                json={**payload, "stream": False},
            )
            if r.status_code < 400:
                return JSONResponse(r.json())
    except Exception:
        pass

    return JSONResponse(_mock_completion(req))


@app.get("/")
def root():
    return {
        "service": "avrone-vllm-shim",
        "docs": "/docs",
        "health": "/health",
        "openai": "/v1/chat/completions",
    }


def main():
    global UPSTREAM
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--upstream", default=UPSTREAM)
    args = parser.parse_args()
    UPSTREAM = args.upstream
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
