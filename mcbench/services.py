# SPDX-License-Identifier: GPL-3.0-or-later
"""Services responsibilities for the local compatibility bench."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcbench import instance_config, server_console
from mcbench.io_utils import atomic, readjson

if TYPE_CHECKING:
    from mcbench.runtime import Runtime


class RuntimeServices:
    """Console, resource telemetry and dashboard status for one runtime."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def memory(self) -> dict[str, float]:
        d = {}
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                d[key] = int(value.split()[0]) * 1024
            return {
                "total_gb": round(d["MemTotal"] / 2**30, 2),
                "available_gb": round(d["MemAvailable"] / 2**30, 2),
            }
        except Exception:
            return {}

    def console_log(self) -> Path:
        p = (
            self.runtime.root
            / "logs"
            / "sessions"
            / self.runtime.instance["key"]
            / "server-commands.jsonl"
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def command_event(self, command: str, output: str, error: bool = False) -> dict[str, Any]:
        record = {
            "time": time.time(),
            "instance": self.runtime.instance["key"],
            "command": command,
            "output": output,
            "error": error,
        }
        with self.runtime.lock:
            self.runtime.console["history"] = (self.runtime.console["history"] + [record])[-30:]
        with self.console_log().open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def run_command(self, command: str, pause: bool = True) -> dict[str, Any]:
        if not instance_config.console_enabled():
            raise ConnectionError("当前实例未配置本地服务器命令接口")
        command = server_console.validate(command)
        with self.runtime.command_lock:
            with self.runtime.lock:
                if pause:
                    self.runtime.state["enabled"] = False
                self.runtime.control_epoch += 1
                self.runtime.history.clear()
                self.runtime.publish_safety()
                atomic(
                    self.runtime.control_file,
                    {"enabled": self.runtime.state["enabled"], "goal": self.runtime.state["goal"]},
                )
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                game = readjson(self.runtime.bridge / "state.json")
                if not game.get("busy") and (not game.get("mining_active")):
                    break
                time.sleep(0.05)
            try:
                output = server_console.execute(command)
                return self.command_event(command, output or "（服务器未返回文字）")
            except (OSError, ValueError, ConnectionError) as exc:
                self.command_event(command, str(exc), True)
                raise

    def server_settings_loop(self) -> None:
        applied_pid = None
        if not instance_config.console_enabled():
            self.runtime.console.update(
                ready=False, settings_applied=True, message="外部服务器：游戏连接不依赖管理权限"
            )
            return
        while not self.runtime.abort.wait(3):
            try:
                pid = (self.runtime.root / "runtime/server.pid").read_text().strip()
                if pid == applied_pid:
                    continue
                with self.runtime.command_lock:
                    results = server_console.apply_defaults()
                    for r in results:
                        self.command_event(r["command"], r["output"])
                self.runtime.console.update(
                    ready=True, settings_applied=True, message="测试设置已应用：和平 · 死亡不掉落"
                )
                atomic(
                    self.runtime.root / "runtime/server-settings-applied.json",
                    {"time": time.time(), "pid": pid, "results": results},
                )
                applied_pid = pid
            except (OSError, ValueError, ConnectionError) as exc:
                self.runtime.console.update(
                    ready=False, settings_applied=False, message="等待服务器命令服务：" + str(exc)
                )

    def telemetry(self) -> None:
        while not self.runtime.abort.wait(5):
            try:
                p = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,memory.total,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                if p.returncode == 0:
                    a = p.stdout.strip().split(",")
                    self.runtime.gpu.update(
                        used_mb=int(a[0]), total_mb=int(a[1]), utilization=int(a[2])
                    )
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        with self.runtime.lock:
            result = dict(self.runtime.state)
        result["game"] = readjson(self.runtime.bridge / "state.json")
        result["intervention"] = self.runtime.intervention.status()
        if time.time() - result["game"].get("timestamp", 0) / 1000 > 10:
            result["game"]["connected"] = False
        result["memory"] = self.memory()
        result["gpu"] = dict(self.runtime.gpu)
        result["model"] = readjson(self.runtime.root / "runtime/model-active.json")
        result["instance"] = {
            k: self.runtime.instance[k]
            for k in ["key", "label", "minecraft_version", "backend", "world_id"]
        }
        result["server_managed"] = instance_config.managed()
        mv = self.runtime.memory.view(self.runtime.state["goal"])
        result["continuation_memory"] = {
            k: mv[k]
            for k in [
                "revision",
                "summary_at",
                "summary_step",
                "pending",
                "running",
                "error",
                "updated_at",
                "prompt_chars",
            ]
        }
        with self.runtime.lock:
            result["console"] = dict(self.runtime.console)
        result["processes"] = {}
        for name in ["server", "client", "model"]:
            if name == "server" and (not instance_config.managed()):
                result["processes"][name] = {
                    "external": True,
                    "alive": bool(result["game"].get("connected")),
                }
                continue
            try:
                pid = int((self.runtime.root / f"runtime/{name}.pid").read_text())
                s = Path(f"/proc/{pid}/status").read_text()
                rss = next(
                    (int(x.split()[1]) / 1024 for x in s.splitlines() if x.startswith("VmRSS:")), 0
                )
                result["processes"][name] = {"pid": pid, "rss_mb": round(rss), "alive": True}
            except Exception:
                result["processes"][name] = {"alive": False}
        result["keep_inventory_command"] = (
            next(
                (c for c in server_console.defaults()["commands"] if c.startswith("gamerule ")),
                "gamerule keepInventory true",
            )
            if instance_config.console_enabled()
            else ""
        )
        result["downloads"] = [
            {"file": p.name, "bytes": p.stat().st_size}
            for p in (self.runtime.root / "models").glob("**/*.incomplete")
        ]
        return result
