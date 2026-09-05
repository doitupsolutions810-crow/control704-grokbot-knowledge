#!/usr/bin/env python3
"""OpenAI-compatible proxy — ChatBot Avrone Due'Krey custom API / vLLM-style gateway."""
from __future__ import annotations

import argparse
import os
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
import uvicorn

app = FastAPI(title="avrone-openai-proxy", version="1.0.0")
UPSTREAM = os.environ.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "openai-proxy",
        "upstream": UPSTREAM.rstrip("/"),
        "key_configured": bool(API_KEY),
        "default_model": DEFAULT_MODEL,
        "mode": "vllm-custom-api",
    }


@app.get("/v1/models")
async def models():
    if not API_KEY:
        return {
            "object": "list",
            "data": [{"id": DEFAULT_MODEL, "object": "model", "owned_by": "avrone"}],
        }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(
            f"{UPSTREAM.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        if r.status_code >= 400:
            return {
                "object": "list",
                "data": [
                    {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
                    {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
                    {"id": "vllm-custom", "object": "model", "owned_by": "avrone"},
                ],
            }
        return r.json()


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    if not API_KEY:
        raise HTTPException(503, "OPENAI_API_KEY not configured")
    url = f"{UPSTREAM.rstrip('/')}/{path}"
    body = await request.body()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": request.headers.get("content-type", "application/json"),
    }
    # Drop hop-by-hop
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.request(
            request.method,
            url,
            content=body,
            headers=headers,
            params=dict(request.query_params),
        )
    ct = r.headers.get("content-type", "application/json")
    if "text/event-stream" in ct:
        return StreamingResponse(r.aiter_bytes(), media_type=ct, status_code=r.status_code)
    return Response(content=r.content, status_code=r.status_code, media_type=ct)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=4000)
    args = p.parse_args()
    if not API_KEY:
        print("[avrone-openai-proxy] WARNING: OPENAI_API_KEY empty")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
