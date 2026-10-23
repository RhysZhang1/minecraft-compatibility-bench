# SPDX-License-Identifier: GPL-3.0-or-later
"""Http responsibilities for the local compatibility bench."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from mcbench import instance_config
from mcbench.feedback import Feedback
from mcbench.io_utils import atomic, readjson

if TYPE_CHECKING:
    from mcbench.runtime import Runtime


class Handler(BaseHTTPRequestHandler):
    """Local HTTP transport; all mutable state belongs to its bound runtime."""

    runtime: Runtime

    def do_GET(self) -> None:
        frame_time = None
        path = urlparse(self.path).path
        if path == "/api/status":
            data = json.dumps(self.runtime.services.status(), ensure_ascii=False).encode()
            mime = "application/json"
        elif path == "/api/instances":
            profiles = []
            for key in instance_config.settings()["instances"]:
                c = instance_config.config(key)
                client = instance_config.path(c["client"]["directory"])
                server = instance_config.path(c["server"]["directory"])
                ready = (client / c["client"]["manifest"]).exists() and (
                    not c["server"].get("managed") or (server / c["server"]["jar"]).exists()
                )
                profiles.append(
                    {
                        "key": key,
                        "label": c["label"],
                        "version": c["minecraft_version"],
                        "installed": ready,
                    }
                )
            data = json.dumps(
                {"selected": self.runtime.instance["key"], "instances": profiles},
                ensure_ascii=False,
            ).encode()
            mime = "application/json"
        elif path == "/api/memory":
            data = json.dumps(
                self.runtime.memory.view(self.runtime.state["goal"]), ensure_ascii=False
            ).encode()
            mime = "application/json"
        elif path == "/frame.jpg":
            try:
                with (self.runtime.bridge / "frame.jpg").open("rb") as f:
                    data = f.read()
                    frame_time = os.fstat(f.fileno()).st_mtime_ns // 1000000
                mime = "image/jpeg"
            except OSError:
                self.send_error(404)
                return
        elif path == "/":
            data = (self.runtime.root / "ui/index.html").read_bytes()
            mime = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        if frame_time is not None:
            self.send_header("X-Frame-Time", str(frame_time))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin not in ["http://127.0.0.1:8790", "http://localhost:8790"]:
            self.send_error(403)
            return
        if self.headers.get("Host") not in ["127.0.0.1:8790", "localhost:8790"]:
            self.send_error(403)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        if self.path not in [
            "/api/control",
            "/api/server/command",
            "/api/memory/save",
            "/api/memory/summarize",
            "/api/memory/checkpoint",
            "/api/instance/switch",
        ]:
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 16384:
                raise ValueError("请求长度无效")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("请求格式无效")
        except (ValueError, UnicodeError):
            self.json_response(400, {"error": "请求格式无效"})
            return
        if self.path == "/api/instance/switch":
            try:
                key = body.get("instance")
                if not isinstance(key, str) or key not in instance_config.settings()["instances"]:
                    raise ValueError("未知实例")
                c = instance_config.config(key)
                if self.runtime.state.get("switching"):
                    raise ValueError("正在切换，请等待观察台重连")
                if (self.runtime.root / "runtime/stop.request").exists():
                    raise ValueError("正在完全停止，请等待结束后再启动")
                if key == self.runtime.instance["key"]:
                    raise ValueError("已经是当前实例")
                if not (
                    instance_config.path(c["client"]["directory"]) / c["client"]["manifest"]
                ).exists():
                    raise ValueError("请先运行setup.sh下载或导入该实例")
                with self.runtime.lock:
                    self.runtime.state["switching"] = True
                    self.runtime.state["enabled"] = False
                    self.runtime.control_epoch += 1
                    self.runtime.publish_safety()
                    self.runtime.memory.checkpoint(
                        self.runtime.state["goal"],
                        readjson(self.runtime.bridge / "state.json"),
                        self.runtime.state["step"],
                        archive=True,
                    )
                    with (self.runtime.root / "logs/switch.log").open("ab") as output:
                        subprocess.Popen(
                            [
                                sys.executable,
                                str(self.runtime.root / "scripts/switch_instance.py"),
                                key,
                            ],
                            cwd=self.runtime.root,
                            stdout=output,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                self.json_response(202, {"ok": True})
                return
            except (OSError, ValueError) as exc:
                self.json_response(400, {"error": str(exc)})
                return
        if self.path == "/api/server/command":
            try:
                self.json_response(
                    200,
                    {
                        "ok": True,
                        "result": self.runtime.services.run_command(
                            body.get("command"), body.get("pause_model", True)
                        ),
                    },
                )
            except ValueError as exc:
                self.json_response(400, {"ok": False, "error": str(exc)})
            except (OSError, ConnectionError) as exc:
                self.json_response(503, {"ok": False, "error": str(exc)})
            return
        if self.path == "/api/memory/save":
            try:
                goal = body.get("goal", self.runtime.state["goal"])
                if not isinstance(goal, str) or not goal.strip() or len(goal) > 600:
                    raise ValueError("目标应为1至600字")
                with self.runtime.lock:
                    self.runtime.memory.save_config(body, goal.strip())
                    self.runtime.state["goal"] = goal.strip()
                    self.runtime.control_epoch += 1
                    self.runtime.history.clear()
                    self.runtime.publish_safety()
                    atomic(
                        self.runtime.control_file,
                        {
                            "enabled": self.runtime.state["enabled"],
                            "goal": self.runtime.state["goal"],
                        },
                    )
                self.json_response(
                    200,
                    {"ok": True, "memory": self.runtime.memory.view(self.runtime.state["goal"])},
                )
            except ValueError as exc:
                self.json_response(400, {"ok": False, "error": str(exc)})
            return
        if self.path == "/api/memory/summarize":
            with self.runtime.memory.lock:
                if not self.runtime.memory.running:
                    self.runtime.memory.pending = True
            self.json_response(202, {"ok": True})
            return
        if self.path == "/api/memory/checkpoint":
            self.runtime.memory.checkpoint(
                self.runtime.state["goal"],
                readjson(self.runtime.bridge / "state.json"),
                self.runtime.state["step"],
                archive=True,
            )
            self.json_response(200, {"ok": True})
            return
        with self.runtime.lock:
            self.runtime.control_epoch += 1
            self.runtime.publish_safety()
            if "enabled" in body:
                self.runtime.state["enabled"] = bool(body["enabled"])
                if self.runtime.state["enabled"]:
                    self.runtime.feedback = Feedback(self.runtime.control_settings)
                    self.runtime.state["recovery_reason"] = ""
                    self.runtime.state["feedback"] = {}
            if "goal" in body:
                self.runtime.state["goal"] = str(body["goal"])[:1000]
                self.runtime.history.clear()
            atomic(
                self.runtime.control_file,
                {"enabled": self.runtime.state["enabled"], "goal": self.runtime.state["goal"]},
            )
        self.json_response(200, {"ok": True})

    def json_response(self, code: int, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


def serve(runtime: Runtime) -> None:
    """Bind a handler per server; importing this module starts nothing."""

    class BoundHandler(Handler):
        pass

    BoundHandler.runtime = runtime
    ThreadingHTTPServer(("127.0.0.1", 8790), BoundHandler).serve_forever()
