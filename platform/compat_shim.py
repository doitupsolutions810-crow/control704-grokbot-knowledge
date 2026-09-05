#!/usr/bin/env python3
"""Optional compatibility shim (:9101) — proxies /v1/agent to orchestrator."""

from __future__ import annotations

import argparse
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="avrone-compat-shim")
UPSTREAM = "http://127.0.0.1:9100"


@app.get("/health")
def health():
    return {"status": "ok", "service": "compat", "upstream": UPSTREAM}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    url = f"{UPSTREAM.rstrip('/')}/{path}"
    body = await request.body()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.request(
            request.method,
            url,
            content=body,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            params=request.query_params,
        )
    return JSONResponse(status_code=r.status_code, content=_safe_json(r))


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:4000]}


@app.post("/v1/agent")
async def agent(request: Request):
    """Wheelhouse-style agent endpoint → create spawn-agent task."""
    data = await request.json()
    goal = data.get("goal") or data.get("input") or data.get("prompt") or "compat task"
    role = data.get("role") or "researcher"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{UPSTREAM.rstrip('/')}/spawn-agent",
            json={"role": role, "goal": str(goal), "tools": data.get("tools") or []},
        )
    return JSONResponse(status_code=r.status_code, content=_safe_json(r))


def main():
    global UPSTREAM
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9101)
    p.add_argument("--upstream", default=UPSTREAM)
    args = p.parse_args()
    UPSTREAM = args.upstream
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
