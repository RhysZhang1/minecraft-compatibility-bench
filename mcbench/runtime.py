# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit runtime construction and shared cancellation/state ownership."""

from __future__ import annotations

import collections
import json
import threading
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.request import Request

from mcbench import instance_config
from mcbench.feedback import Feedback
from mcbench.io_utils import atomic, readjson
from mcbench.memory import WorldMemory

if TYPE_CHECKING:
    from mcbench.runtime import Runtime

from urllib.request import ProxyHandler, build_opener

from mcbench.http import serve
from mcbench.paths import ROOT


class Runtime:
    """Own one world's mutable state and explicitly compose runtime services."""

    def __init__(self, root: Path, instance: dict | None = None) -> None:
        self.root = Path(root)
        self.bridge = self.root / "runtime/bridge"
        self.engine = "http://127.0.0.1:8789"
        self.instance = instance if instance is not None else instance_config.config()
        self.control_settings = readjson(self.root / "control-settings.json")
        self.control_file = instance_config.path(self.instance["control_file"], self.root)
        self.episodes = instance_config.path(self.instance["episodes_directory"], self.root)
        self.state = {
            "phase": "Waiting for client and model",
            "enabled": True,
            "step": 0,
            "raw": "",
            "thinking": "",
            "last_action": "",
            "latency": 0,
            "errors": 0,
            "parsed": 0,
            "history": [],
            "goal": self.instance["initial_goal"],
            "inference_started": None,
            "feedback": {},
            "recovery_reason": "",
        }
        self.lock = threading.RLock()
        self.history = collections.deque(maxlen=self.control_settings.get("history_length", 5))
        self.abort = threading.Event()
        self.control_epoch = int(time.time() * 1000)
        self.command_lock = threading.Lock()
        self.console = {
            "ready": False,
            "settings_applied": False,
            "message": "Waiting for command service",
            "history": [],
        }
        self.opener = build_opener(ProxyHandler({}))
        self.memory = WorldMemory(
            self.root,
            instance_config.path(self.instance["memory_directory"], self.root),
            self.instance["world_id"],
        )
        self.feedback = Feedback(self.control_settings)
        self.marker_cache = {}
        self.gpu = {}
        from mcbench.intervention import Intervention
        from mcbench.loop import DecisionLoop
        from mcbench.prompt import PromptBuilder
        from mcbench.services import RuntimeServices

        self.prompt = PromptBuilder(self)
        self.loop = DecisionLoop(self)
        self.services = RuntimeServices(self)
        self.intervention = Intervention(self)

    def request(self, path: str, body: dict[str, Any] | None = None, timeout: float = 10) -> Any:
        req = Request(
            self.engine + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        return self.opener.open(req, timeout=timeout)

    def publish_safety(self) -> None:
        with self.lock:
            atomic(
                self.bridge / "safety.json",
                {"epoch": self.control_epoch, "timestamp": int(time.time() * 1000)},
            )

    def safety_loop(self) -> None:
        while not self.abort.is_set():
            try:
                self.publish_safety()
            except OSError:
                traceback.print_exc()
            self.abort.wait(0.25)

    def event(self, kind: str, **values: Any) -> None:
        record = {"time": time.time(), "kind": kind, **values}
        with self.lock:
            self.state["history"] = (self.state["history"] + [record])[-30:]
        with (self.root / "logs/events.jsonl").open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def main(self) -> None:
        self.bridge.mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(exist_ok=True)
        saved = readjson(self.control_file)
        self.state.update({key: saved[key] for key in ["enabled", "goal"] if key in saved})
        try:
            records = [
                json.loads(line)
                for line in self.services.console_log().read_text().splitlines()[-30:]
            ]
            self.console["history"] = records
        except (OSError, ValueError):
            pass
        records = [readjson(p) for p in sorted(self.episodes.glob("*.json"))]
        if records:
            last = records[-1]
            self.state.update(
                step=max((r.get("step", 0) for r in records)),
                parsed=sum((bool(r.get("parsed")) for r in records)),
                raw=last.get("raw", ""),
                thinking=last.get("reasoning", ""),
                last_action=last.get("action", ""),
                latency=last.get("latency", 0),
            )
            self.state["history"] = [
                dict(time=r.get("timestamp", time.time()), kind="decision", **r)
                for r in records[-10:]
            ]
        self.memory.ensure(self.state["goal"])
        self.memory.checkpoint(
            self.state["goal"], readjson(self.bridge / "state.json"), self.state["step"]
        )
        self.publish_safety()
        threading.Thread(target=self.safety_loop, daemon=True).start()
        threading.Thread(target=self.loop.loop, daemon=True).start()
        threading.Thread(target=self.services.telemetry, daemon=True).start()
        threading.Thread(target=self.services.server_settings_loop, daemon=True).start()
        print("Minecraft monitor: http://127.0.0.1:8790", flush=True)
        serve(self)


def main() -> None:
    Runtime(ROOT).main()


if __name__ == "__main__":
    main()
