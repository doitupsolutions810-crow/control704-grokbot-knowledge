#!/usr/bin/env python3
"""Lightweight static/file server for orchestrator artifacts (:9102)."""

from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="avrone-artifacts")
ROOT = Path(".")


@app.get("/health")
def health():
    return {"status": "ok", "service": "artifacts", "root": str(ROOT)}


@app.get("/")
def index():
    files = [p.name for p in ROOT.iterdir() if p.is_file() and not p.name.startswith(".")]
    return {"artifacts": files, "count": len(files)}


@app.get("/files/{name}")
def get_file(name: str):
    path = ROOT / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)


def main():
    global ROOT
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9102)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    ROOT = args.root
    ROOT.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(ROOT)), name="static")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
