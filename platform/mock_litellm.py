#!/usr/bin/env python3
"""Minimal OpenAI-compatible mock used when LiteLLM package is unavailable."""

from __future__ import annotations

import argparse
import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="avrone-mock-litellm")


class Msg(BaseModel):
    role: str
    content: str


class Req(BaseModel):
    model: str = "mock-gpt"
    messages: list[Msg]
    temperature: float = 0.2
    stream: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-litellm"}


@app.get("/v1/models")
def models():
    return {
        "object": "list",
        "data": [{"id": "mock-gpt", "object": "model", "owned_by": "avrone-mock"}],
    }


@app.post("/v1/chat/completions")
def chat(req: Req) -> dict[str, Any]:
    last = req.messages[-1].content if req.messages else ""
    text = (
        f"[mock-litellm] ChatBot Avrone Due'Krey: received {last[:300]!r}. "
        "Wire OPENAI_API_KEY / real providers in configs/litellm_config.yaml for live models."
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:10]}",
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=4000)
    args = p.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
