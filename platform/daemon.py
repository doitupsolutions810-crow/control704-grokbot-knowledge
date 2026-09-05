#!/usr/bin/env python3
"""avrone-duekrey-daemon — process supervisor for ChatBot Avrone Due'Krey."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PLATFORM = Path(__file__).resolve().parent
ORCH = ROOT / "orchestrator"
PID_DIR = PLATFORM / "run"
LOG_DIR = PLATFORM / "logs"
STATE_FILE = PID_DIR / "daemon_state.json"
PORTS_FILE = PID_DIR / "ports.json"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        # File values win so avrone.env updates apply on restart
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(preferred: int, reserved: set[int] | None = None, host: str = "127.0.0.1") -> int:
    reserved = reserved or set()
    for p in [preferred] + list(range(preferred + 1, preferred + 50)):
        if p in reserved:
            continue
        if port_free(p, host):
            reserved.add(p)
            return p
    raise RuntimeError(f"no free port near {preferred}")


@dataclass
class Service:
    name: str
    port: int
    cmd: list[str]
    cwd: Optional[Path] = None
    env: dict[str, str] = field(default_factory=dict)
    pid: Optional[int] = None
    optional: bool = False


class Daemon:
    def __init__(self, env_file: Optional[Path] = None, reuse_ports: bool = True):
        PID_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if env_file:
            load_env_file(env_file)
        else:
            # Orchestrator .env first; platform avrone.env wins for host flags
            load_env_file(ORCH / ".env")
            load_env_file(PLATFORM / "configs" / "avrone.env")

        saved = self._load_ports() if reuse_ports else None
        reserved: set[int] = set()
        defaults = {
            "vllm": int(os.environ.get("VLLM_PORT", "8000")),
            "litellm": int(os.environ.get("LITELLM_PORT", "4000")),
            "orchestrator": int(
                os.environ.get("ORCHESTRATOR_PORT", os.environ.get("PORT", "9100"))
            ),
            "compat": int(os.environ.get("COMPAT_PORT", "9101")),
            "artifacts": int(os.environ.get("ARTIFACT_PORT", "9102")),
        }

        self.ports: dict[str, int] = {}
        if saved and all(k in saved for k in defaults):
            # Prefer saved ports if those services are still running, else re-pick
            for name, preferred in defaults.items():
                if self.is_running(name) and name in saved:
                    self.ports[name] = int(saved[name])
                    reserved.add(self.ports[name])
                else:
                    # If saved port free, keep it for stability
                    cand = int(saved.get(name, preferred))
                    if cand not in reserved and port_free(cand):
                        self.ports[name] = cand
                        reserved.add(cand)
                    else:
                        self.ports[name] = pick_port(preferred, reserved)
        else:
            for name, preferred in defaults.items():
                self.ports[name] = pick_port(preferred, reserved)

        os.environ["VLLM_PORT"] = str(self.ports["vllm"])
        os.environ["LITELLM_PORT"] = str(self.ports["litellm"])
        os.environ["ORCHESTRATOR_PORT"] = str(self.ports["orchestrator"])
        os.environ["COMPAT_PORT"] = str(self.ports["compat"])
        os.environ["ARTIFACT_PORT"] = str(self.ports["artifacts"])
        os.environ.setdefault(
            "LLM_BASE_URL",
            f"http://127.0.0.1:{self.ports['litellm']}/v1",
        )
        os.environ.setdefault("PORT", str(self.ports["orchestrator"]))
        os.environ.setdefault(
            "AVRONE_BASE_URL", f"http://127.0.0.1:{self.ports['orchestrator']}"
        )

        py = self._python()
        litellm_bin = Path(py).parent / "litellm"
        litellm_cfg = PLATFORM / "configs" / "litellm_config.yaml"
        artifacts_dir = ORCH / "data" / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        use_real_litellm = os.environ.get("AVRONE_USE_LITELLM", "0") in ("1", "true", "TRUE")
        has_provider_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("XAI_API_KEY"))
        # Prefer direct OpenAI-compatible proxy (vLLM custom API) when a provider key is set.
        # Full LiteLLM CLI proxy often requires Prisma/Postgres; keep as optional override.
        use_litellm_cli = os.environ.get("AVRONE_LITELLM_CLI", "0") in ("1", "true", "TRUE")
        if use_real_litellm and has_provider_key and not use_litellm_cli:
            litellm_cmd = [
                py,
                str(PLATFORM / "openai_proxy.py"),
                "--host",
                "0.0.0.0",
                "--port",
                str(self.ports["litellm"]),
            ]
        elif use_real_litellm and use_litellm_cli and litellm_bin.is_file():
            litellm_cmd = [
                str(litellm_bin),
                "--config",
                str(litellm_cfg),
                "--host",
                "0.0.0.0",
                "--port",
                str(self.ports["litellm"]),
            ]
        else:
            litellm_cmd = [
                py,
                str(PLATFORM / "mock_litellm.py"),
                "--host",
                "0.0.0.0",
                "--port",
                str(self.ports["litellm"]),
            ]

        self.services: list[Service] = [
            Service(
                name="litellm",
                port=self.ports["litellm"],
                cmd=litellm_cmd,
                cwd=PLATFORM,
                optional=True,
            ),
            Service(
                name="vllm",
                port=self.ports["vllm"],
                cmd=[
                    py,
                    str(PLATFORM / "vllm_shim.py"),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(self.ports["vllm"]),
                    "--upstream",
                    f"http://127.0.0.1:{self.ports['litellm']}/v1",
                ],
                cwd=PLATFORM,
            ),
            Service(
                name="orchestrator",
                port=self.ports["orchestrator"],
                cmd=[
                    py,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(self.ports["orchestrator"]),
                ],
                cwd=ORCH,
                env={
                    "LLM_BASE_URL": os.environ["LLM_BASE_URL"],
                    "PORT": str(self.ports["orchestrator"]),
                    "ORCHESTRATOR_PORT": str(self.ports["orchestrator"]),
                    "LITELLM_PORT": str(self.ports["litellm"]),
                    "VLLM_PORT": str(self.ports["vllm"]),
                    "ARTIFACT_PORT": str(self.ports["artifacts"]),
                    "COMPAT_PORT": str(self.ports["compat"]),
                    "ALLOW_AGENT_EXECUTION": os.environ.get(
                        "ALLOW_AGENT_EXECUTION", "false"
                    ),
                    "KNOWLEDGE_ROOT": str(ROOT),
                },
            ),
            Service(
                name="artifacts",
                port=self.ports["artifacts"],
                cmd=[
                    py,
                    str(PLATFORM / "artifact_server.py"),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(self.ports["artifacts"]),
                    "--root",
                    str(artifacts_dir),
                ],
                cwd=PLATFORM,
            ),
            Service(
                name="compat",
                port=self.ports["compat"],
                cmd=[
                    py,
                    str(PLATFORM / "compat_shim.py"),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(self.ports["compat"]),
                    "--upstream",
                    f"http://127.0.0.1:{self.ports['orchestrator']}",
                ],
                cwd=PLATFORM,
                optional=True,
            ),
        ]
        self._stopping = False

    def _python(self) -> str:
        venv = PLATFORM / ".venv" / "bin" / "python"
        if venv.is_file():
            return str(venv)
        orch_venv = ORCH / ".venv" / "bin" / "python"
        if orch_venv.is_file():
            return str(orch_venv)
        return sys.executable

    def _log_path(self, name: str) -> Path:
        return LOG_DIR / f"{name}.log"

    def _pid_path(self, name: str) -> Path:
        return PID_DIR / f"{name}.pid"

    def _load_ports(self) -> Optional[dict]:
        if PORTS_FILE.is_file():
            try:
                return json.loads(PORTS_FILE.read_text())
            except json.JSONDecodeError:
                return None
        if STATE_FILE.is_file():
            try:
                return json.loads(STATE_FILE.read_text()).get("ports")
            except json.JSONDecodeError:
                return None
        return None

    def _save_ports(self) -> None:
        PORTS_FILE.write_text(json.dumps(self.ports, indent=2))

    def start_service(self, svc: Service) -> bool:
        if self.is_running(svc.name):
            print(f"[avrone] {svc.name} already running")
            return True
        logf = self._log_path(svc.name).open("a", buffering=1)
        env = os.environ.copy()
        env.update(svc.env)
        if svc.name == "litellm":
            # LiteLLM proxy DB features need Postgres; avoid sqlite DATABASE_URL
            env.pop("DATABASE_URL", None)
            env.setdefault("STORE_MODEL_IN_DB", "False")
        try:
            proc = subprocess.Popen(
                svc.cmd,
                cwd=str(svc.cwd) if svc.cwd else None,
                env=env,
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as exc:
            print(f"[avrone] failed to start {svc.name}: {exc}")
            if svc.optional or svc.name == "litellm":
                return self._start_fallback(svc, logf)
            return False

        time.sleep(1.0)
        if proc.poll() is not None:
            print(
                f"[avrone] {svc.name} exited early code={proc.returncode} — see {self._log_path(svc.name)}"
            )
            if svc.optional or svc.name == "litellm":
                return self._start_fallback(svc, logf)
            return False

        self._pid_path(svc.name).write_text(str(proc.pid))
        svc.pid = proc.pid
        # Health probe for litellm — fall back to mock if still down
        if svc.name == "litellm" and not self._wait_health(svc.port, timeout=12.0):
            print(f"[avrone] litellm not healthy on :{svc.port} — switching to mock")
            self.stop_service(svc.name)
            return self._start_fallback(svc, logf)
        print(f"[avrone] started {svc.name} pid={proc.pid} port={svc.port}")
        return True

    def _wait_health(self, port: int, timeout: float = 12.0) -> bool:
        import urllib.request
        deadline = time.time() + timeout
        url = f"http://127.0.0.1:{port}/health"
        while time.time() < deadline:
            if not self.is_running("litellm") and not port_free(port):
                # process may have died; pid file stale
                pass
            try:
                with urllib.request.urlopen(url, timeout=0.5) as r:
                    if r.status < 500:
                        return True
            except Exception:
                time.sleep(0.25)
        return False

    def _start_fallback(self, svc: Service, logf) -> bool:
        if svc.name != "litellm":
            return False
        py = self._python()
        cmd = [
            py,
            str(PLATFORM / "mock_litellm.py"),
            "--host",
            "0.0.0.0",
            "--port",
            str(svc.port),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PLATFORM),
                env=os.environ.copy(),
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as exc:
            print(f"[avrone] mock litellm failed: {exc}")
            return False
        time.sleep(0.6)
        if proc.poll() is not None:
            print("[avrone] mock litellm exited early")
            return False
        self._pid_path(svc.name).write_text(str(proc.pid))
        svc.pid = proc.pid
        print(f"[avrone] started mock litellm pid={proc.pid} port={svc.port}")
        return True

    def is_running(self, name: str) -> bool:
        path = self._pid_path(name)
        if not path.is_file():
            return False
        try:
            pid = int(path.read_text().strip())
        except ValueError:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            path.unlink(missing_ok=True)
            return False

    def stop_service(self, name: str) -> None:
        path = self._pid_path(name)
        if not path.is_file():
            print(f"[avrone] {name} not running")
            return
        try:
            pid = int(path.read_text().strip())
        except ValueError:
            path.unlink(missing_ok=True)
            return
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.15)
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        print(f"[avrone] stopped {name}")

    def start_all(self) -> int:
        ok = True
        order = ["litellm", "vllm", "artifacts", "orchestrator", "compat"]
        by_name = {s.name: s for s in self.services}
        for name in order:
            svc = by_name[name]
            if not self.start_service(svc):
                if not svc.optional:
                    ok = False
        self._save_ports()
        self._write_state()
        self.status()
        return 0 if ok else 1

    def stop_all(self) -> None:
        for name in ["compat", "orchestrator", "artifacts", "vllm", "litellm"]:
            self.stop_service(name)

    def status(self) -> dict:
        info = {
            "product": "ChatBot Avrone Due'Krey",
            "daemon": "avrone-duekrey-daemon",
            "ports": self.ports,
            "base_url": f"http://127.0.0.1:{self.ports['orchestrator']}",
            "services": {},
        }
        for svc in self.services:
            running = self.is_running(svc.name)
            info["services"][svc.name] = {
                "running": running,
                "port": self.ports[svc.name],
                "pid_file": str(self._pid_path(svc.name)),
            }
            mark = "UP" if running else "DOWN"
            print(f"  {svc.name:14} {mark:4} :{self.ports[svc.name]}")
        STATE_FILE.write_text(json.dumps(info, indent=2))
        self._save_ports()
        print(f"[avrone] state -> {STATE_FILE}")
        print(f"[avrone] HUD  -> http://127.0.0.1:{self.ports['orchestrator']}/")
        return info

    def _write_state(self) -> None:
        STATE_FILE.write_text(
            json.dumps(
                {
                    "product": "ChatBot Avrone Due'Krey",
                    "daemon": "avrone-duekrey-daemon",
                    "ports": self.ports,
                    "base_url": f"http://127.0.0.1:{self.ports['orchestrator']}",
                },
                indent=2,
            )
        )

    def supervise(self) -> int:
        self.start_all()
        print("[avrone] supervising (Ctrl+C to stop)")

        def _handle(sig, frame):
            self._stopping = True

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)
        try:
            while not self._stopping:
                for svc in self.services:
                    if not self.is_running(svc.name):
                        print(f"[avrone] restarting {svc.name}")
                        self.start_service(svc)
                time.sleep(3)
        finally:
            self.stop_all()
        return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avrone-daemon", description="avrone-duekrey-daemon"
    )
    parser.add_argument(
        "action", choices=["start", "stop", "restart", "status", "supervise"]
    )
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args(argv)
    # status/stop should reuse saved ports; start may refresh if nothing running
    reuse = args.action in ("status", "stop", "restart", "supervise")
    d = Daemon(env_file=args.env_file, reuse_ports=reuse or True)
    if args.action == "start":
        return d.start_all()
    if args.action == "stop":
        d.stop_all()
        return 0
    if args.action == "restart":
        d.stop_all()
        time.sleep(0.5)
        return Daemon(env_file=args.env_file, reuse_ports=False).start_all()
    if args.action == "status":
        d.status()
        return 0
    if args.action == "supervise":
        return d.supervise()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
