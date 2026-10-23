# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded human input through the same isolated client as model actions."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from mcbench.feedback import Feedback, read_observation
from mcbench.io_utils import atomic, readjson

if TYPE_CHECKING:
    from mcbench.runtime import Runtime

KEYS = frozenset(
    {
        "W",
        "A",
        "S",
        "D",
        "E",
        "Q",
        "Esc",
        "Space",
        "Shift",
        "Ctrl",
        "LB",
        "RB",
        "MB",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
    }
)


class InterventionBusy(ValueError):
    """Another operation currently owns the input/console channel."""


class InputTarget(Protocol):
    def apply(self, keys: set[str]) -> None: ...
    def point(self, x: float, y: float) -> None: ...
    def move(self, dx: float, dy: float, scroll: int) -> None: ...


def point(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("点击位置必须包含两个归一化坐标")
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not 0 <= v <= 1
        or not math.isfinite(v)
        for v in value
    ):
        raise ValueError("画面坐标应在0到1之间")
    return list(value)


def build_plan(body: dict[str, Any]) -> dict[str, Any]:
    """Validate a small input vocabulary, never arbitrary shell code or macros."""
    kind = body.get("kind")
    duration = body.get("duration_ms", 300)
    if isinstance(duration, bool) or not isinstance(duration, int) or not 50 <= duration <= 2000:
        raise ValueError("手动动作时长应为50到2000毫秒")
    events: list[dict[str, Any]] = []
    if kind in ("click", "drag"):
        button = body.get("button", "LB")
        if button not in ("LB", "RB"):
            raise ValueError("请选择鼠标左键或右键")
        if not isinstance(body.get("shift", False), bool):
            raise ValueError("Shift选项无效")
        modifiers = ["Shift"] if body.get("shift") else []
        start = point(body.get("point"))
        events = [
            {"at": 0, "point": start, "keys": []},
            {"at": 40, "keys": modifiers},
            {"at": 80, "keys": [*modifiers, button]},
        ]
        if kind == "drag":
            end = point(body.get("end"))
            for step in range(1, 21):
                ratio = step / 20
                events.append(
                    {
                        "at": 100 + round(duration * ratio),
                        "point": [start[i] + (end[i] - start[i]) * ratio for i in range(2)],
                    }
                )
            finish = duration + 180
        else:
            finish = 200
        events.append({"at": finish, "keys": []})
        gui = True
    elif kind == "key":
        keys = body.get("keys")
        if (
            not isinstance(keys, list)
            or not 1 <= len(keys) <= 4
            or any(not isinstance(k, str) or k not in KEYS for k in keys)
        ):
            raise ValueError("请选择1至4个支持的游戏按键")
        events = [{"at": 0, "keys": keys}, {"at": duration, "keys": []}]
        finish, gui = duration, None
    elif kind == "look":
        mouse = body.get("mouse")
        if (
            not isinstance(mouse, list)
            or len(mouse) != 2
            or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or abs(v) > 250
                or not math.isfinite(v)
                for v in mouse
            )
        ):
            raise ValueError("视角位移应为两个-250至250之间的数值")
        events = [{"at": 0, "motion": mouse}, {"at": 100, "keys": []}]
        finish, gui = 100, False
    elif kind == "scroll":
        delta = body.get("delta")
        if isinstance(delta, bool) or not isinstance(delta, int) or not 1 <= abs(delta) <= 5:
            raise ValueError("滚轮步数应为-5至5之间的非零整数")
        events = [{"at": 0, "scroll": delta}, {"at": 100, "keys": []}]
        finish, gui = 100, None
    else:
        raise ValueError("不支持的手动动作")
    return {"kind": kind, "events": events, "duration_ms": finish, "gui": gui}


@dataclass
class ManualPlayback:
    """An input timeline that always releases on completion or cancellation."""

    plan: dict[str, Any]
    started: float
    session: str
    screen: str
    index: int = 0
    finished: bool = False

    def tick(
        self, now: float, target: InputTarget, game: dict[str, Any], valid: bool
    ) -> dict[str, Any] | None:
        if self.finished:
            return None
        reason = ""
        if not valid:
            reason = "control changed or heartbeat expired"
        elif game.get("session") != self.session:
            reason = "client session changed"
        elif game.get("screen") != self.screen:
            reason = "screen changed"
        elif now - self.started > self.plan["duration_ms"] + 1000:
            reason = "manual deadline exceeded"
        if reason:
            target.apply(set())
            self.finished = True
            return {"cancelled": True, "reason": reason}
        elapsed = now - self.started
        while (
            self.index < len(self.plan["events"])
            and self.plan["events"][self.index]["at"] <= elapsed
        ):
            event = self.plan["events"][self.index]
            if "keys" in event:
                target.apply(set(event["keys"]))
            if "point" in event:
                target.point(*event["point"])
            if "motion" in event or "scroll" in event:
                target.move(*event.get("motion", [0, 0]), event.get("scroll", 0))
            self.index += 1
        if elapsed >= self.plan["duration_ms"]:
            target.apply(set())
            self.finished = True
            return {"cancelled": False, "reason": "completed"}
        return None


class Intervention:
    """Serialize human actions, invalidate model outputs, and retain provenance."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.active = False
        self.last: dict[str, Any] = {}

    def pause(self) -> int:
        with self.runtime.lock:
            self.runtime.state["enabled"] = False
            self.runtime.control_epoch += 1
            self.runtime.history.clear()
            self.runtime.feedback = Feedback(self.runtime.control_settings)
            self.runtime.feedback.last = "A human intervened. Re-check the fresh image; do not assume the objective is complete."
            self.runtime.state.update(feedback={}, recovery_reason="临时人工干预；自动操作保持暂停")
            self.runtime.publish_safety()
            atomic(
                self.runtime.control_file, {"enabled": False, "goal": self.runtime.state["goal"]}
            )
            return self.runtime.control_epoch

    def release(self) -> dict[str, Any]:
        self.pause()
        return {"released": True, "message": "已请求暂停模型并释放全部输入"}

    def status(self) -> dict[str, Any]:
        game = readjson(self.runtime.bridge / "state.json")
        capabilities = game.get("capabilities", {})
        return {
            "supported": bool(
                self.runtime.instance["backend"] == "virtual-x11"
                and isinstance(capabilities, dict)
                and capabilities.get("manual_input")
            ),
            "active": self.active,
            "last": self.last,
        }

    def run(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("kind") == "release":
            return self.release()
        plan = build_plan(body)
        if not self.status()["supported"]:
            raise ValueError("当前输入后端未提供临时控制；此功能需要更新后的独立虚拟显示后端")
        if not self.runtime.command_lock.acquire(blocking=False):
            raise InterventionBusy("已有手动动作或服务器命令正在执行，请稍候或释放输入")
        record: dict[str, Any] = {
            "source": "human",
            "plan": plan,
            "executed": False,
            "timestamp": time.time(),
        }
        epoch = None
        folder = self.runtime.episodes.parent / "interventions"
        ident = time.time_ns()
        try:
            with self.runtime.lock:
                self.active = True
                epoch = self.runtime.control_epoch + 1
                epoch = self.pause()
            deadline = time.monotonic() + 2
            while True:
                game = readjson(self.runtime.bridge / "state.json")
                if (
                    0 <= time.time() * 1000 - game.get("timestamp", 0) < 1500
                    and not game.get("busy")
                    and not game.get("mining_active")
                    and not game.get("held_keys")
                ):
                    break
                if self.runtime.abort.wait(0.02) or time.monotonic() >= deadline:
                    raise TimeoutError("客户端未确认释放输入，未发送手动动作")
            if (
                not game.get("connected")
                or body.get("session") != game.get("session")
                or body.get("screen") != game.get("screen")
            ):
                raise ValueError("客户端或界面已变化，请查看新画面后重试")
            gui = bool(game.get("screen"))
            if plan["gui"] is not None and (
                not game.get("screen_known", False) or gui != plan["gui"]
            ):
                raise ValueError("画面点击/拖动仅用于已识别界面；游戏内转向请用视角按钮")
            before = read_observation(self.runtime.bridge)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{ident}.before.jpg").write_bytes(before.image)
            record["game_before"] = before.game
            with self.runtime.lock:
                if epoch != self.runtime.control_epoch or self.runtime.abort.is_set():
                    raise InterruptedError("手动操作已取消")
                command_id = max(
                    int(time.time() * 1000),
                    game.get("command_id", 0) + 1,
                    readjson(self.runtime.bridge / "command.json").get("id", 0) + 1,
                )
                atomic(
                    self.runtime.bridge / "command.json",
                    {
                        "id": command_id,
                        "epoch": epoch,
                        "source": "human",
                        "session": game["session"],
                        "screen": game["screen"],
                        "manual": plan,
                    },
                )
            record["command_id"] = command_id
            deadline = time.monotonic() + 5
            while True:
                done = readjson(self.runtime.bridge / "completed.json")
                if done.get("id") == command_id:
                    record["completion"] = done
                    record["executed"] = not done.get("cancelled", True)
                    break
                if self.runtime.abort.wait(0.02) or epoch != self.runtime.control_epoch:
                    raise InterruptedError("手动输入已释放或取消")
                if time.monotonic() >= deadline:
                    raise TimeoutError("客户端未确认手动动作完成，已请求释放")
            try:
                after = read_observation(self.runtime.bridge, after=done["time"], timeout=3)
                (folder / f"{ident}.after.jpg").write_bytes(after.image)
                record["game_after"] = after.game
                self.runtime.memory.checkpoint(
                    self.runtime.state["goal"], after.game, self.runtime.state["step"]
                )
            except (OSError, TimeoutError) as exc:
                record["observation_error"] = str(exc)
            return record
        except Exception as exc:
            record["error"] = str(exc)
            raise
        finally:
            try:
                with self.runtime.lock:
                    if epoch is not None and epoch == self.runtime.control_epoch:
                        self.runtime.control_epoch += 1
                        self.runtime.publish_safety()
            finally:
                with self.runtime.lock:
                    self.active = False
                    self.last = record
                self.runtime.command_lock.release()
            folder.mkdir(parents=True, exist_ok=True)
            atomic(folder / f"{ident}.json", record)
            self.runtime.event("intervention", message="临时人工干预；模型保持暂停", result=record)
