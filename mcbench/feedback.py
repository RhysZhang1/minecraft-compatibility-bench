# SPDX-License-Identifier: GPL-3.0-or-later
"""Generic observation/action feedback; no pack names, recipes or button choices."""

from __future__ import annotations

import io
import json
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from gamescaling.action import Action
from PIL import Image


@dataclass
class Observation:
    image: bytes
    metadata: dict[str, Any]
    game: dict[str, Any]


def json_file(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def read_observation(
    folder: str | Path,
    after: float = 0,
    timeout: float = 3,
    cancel: Callable[[], bool] = lambda: False,
) -> Observation:
    """Match metadata to an atomically published image, then require freshness."""
    folder = Path(folder)
    deadline = time.monotonic() + timeout
    while not cancel():
        meta = json_file(folder / "frame-meta.json")
        game = json_file(folder / "state.json")
        now = time.time() * 1000
        if (
            meta.get("captured_at", 0) > after
            and game.get("timestamp", 0) >= after
            and game.get("connected")
            and 0 <= now - meta.get("captured_at", 0) < 1500
            and 0 <= now - game.get("timestamp", 0) < 1500
        ):
            try:
                with (folder / "frame.jpg").open("rb") as f:
                    data = f.read()
                    modified = os.fstat(f.fileno()).st_mtime_ns // 1000000
                if meta.get("image_mtime_ms") == modified and meta.get("session") == game.get(
                    "session"
                ):
                    return Observation(data, meta, game)
            except OSError:
                pass
        if time.monotonic() >= deadline:
            raise TimeoutError("未取得动作完成后的新画面；不重复使用旧截图")
        time.sleep(0.015)
    raise InterruptedError("控制状态已变化")


def visual(image: bytes) -> bytes:
    # Exclude most HUD and use coarse luminance; tiny cursor changes are not progress.
    with Image.open(io.BytesIO(image)) as im:
        im = im.convert("L")
        im = im.crop((0, 0, im.width, int(im.height * 0.82))).resize((32, 18))
        return bytes((v // 16) * 16 for v in im.tobytes())


def inventory(game: dict[str, Any]) -> list[tuple] | None:
    if "inventory" not in game or game.get("inventory_error"):
        return None
    return sorted((i.get("slot"), i.get("item"), i.get("count")) for i in game["inventory"])


def changes(before: Observation, after: Observation) -> tuple[list[str], float]:
    a, b = before.game, after.game
    reasons = []
    if a.get("session") != b.get("session"):
        reasons.append("client reconnected")
    if (
        a.get("screen_known", "screen" in a)
        and b.get("screen_known", "screen" in b)
        and a.get("screen") != b.get("screen")
    ):
        reasons.append("screen changed")
    if inventory(a) is not None and inventory(b) is not None and inventory(a) != inventory(b):
        reasons.append("inventory changed")
    if "health" in a and "health" in b and a["health"] != b["health"]:
        reasons.append("health changed")
    if (
        all(k in a and k in b for k in ("x", "y", "z"))
        and sum((a[k] - b[k]) ** 2 for k in ("x", "y", "z")) > 0.04
    ):
        reasons.append("position changed")
    ta, tb = a.get("target_block", {}), b.get("target_block", {})
    if (
        ta
        and (ta.get("x"), ta.get("y"), ta.get("z")) == (tb.get("x"), tb.get("y"), tb.get("z"))
        and ta.get("block") != tb.get("block")
    ):
        reasons.append("target block changed")
    va, vb = visual(before.image), visual(after.image)
    distance = sum(abs(x - y) for x, y in zip(va, vb)) / len(va)
    if distance > 5:
        reasons.append("visible scene changed")
    return reasons, distance


class Feedback:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        self.streak = 0
        self.noops = 0
        self.recoveries = 0
        self.last = "No action result yet."
        self.last_action = ""
        self.phase = "observing"
        self.reset_history = False
        self.scenes = deque(maxlen=6)

    def record(
        self, before: Observation, after: Observation, action: Action, executed: bool = True
    ) -> dict[str, Any]:
        observed, distance = changes(before, after)
        if not executed:
            self.last = "Previous action was cancelled, not completed."
            self.reset_history = False
            return {
                "changes": [],
                "visual_difference": round(distance, 2),
                "stagnant_decisions": self.streak,
                "noop_streak": self.noops,
                "recoveries": self.recoveries,
                "phase": self.phase,
                "executed": False,
            }
        self.noops = self.noops + 1 if action.is_noop else 0
        g = after.game
        signature = (
            g.get("screen", ""),
            tuple(inventory(g)) if inventory(g) is not None else ("unknown",),
            tuple(round(g.get(k, 0), 1) for k in ("x", "y", "z")),
            g.get("health"),
        )
        self.scenes.append(signature)
        cycle = (
            len(self.scenes) == 6
            and len({s[0] for s in self.scenes}) == 2
            and len(set(self.scenes)) == 2
            and all(self.scenes[i] == self.scenes[i % 2] for i in range(6))
        )
        self.streak = 0 if observed and not cycle else self.streak + 1
        self.last_action = action.history_text
        self.last = (
            "Repeated return to the same two screens without inventory or position change."
            if cycle
            else "; ".join(observed)
            if observed
            else "No substantial observed change after the previous action."
        )
        if observed and not cycle:
            self.recoveries = 0
            self.phase = "observing"
        self.reset_history = False
        limit = self.settings.get("stalled_decisions", 6)
        if self.streak and self.streak % limit == 0:
            self.recoveries += 1
            self.reset_history = True
            self.phase = "reassess"
            if self.recoveries > self.settings.get("recovery_attempts", 2):
                self.phase = "stalled"
        return {
            "changes": observed,
            "visual_difference": round(distance, 2),
            "stagnant_decisions": self.streak,
            "noop_streak": self.noops,
            "recoveries": self.recoveries,
            "phase": self.phase,
            "screen_cycle_detected": cycle,
            "executed": executed,
        }

    def text(self, game: dict[str, Any]) -> str:
        cursor = game.get("cursor", {})
        lines = [
            "Observed screen: "
            + (
                (game.get("screen") or "in game")
                if game.get("screen_known", "screen" in game)
                else "unknown; use the image"
            )
            + ".",
            "Previous result: " + self.last,
            "Consecutive decisions without substantial observed change: " + str(self.streak) + ".",
        ]
        if game.get("screen") or not game.get("screen_known", "screen" in game):
            lines += [
                "Virtual cursor in screenshot pixels: "
                + str(cursor.get("x", "unknown"))
                + ", "
                + str(cursor.get("y", "unknown"))
                + ". Mouse actions are relative displacements, not absolute positions."
            ]
        if self.phase in ("reassess", "stalled"):
            lines += [
                "Reassess the fresh image and the last result before choosing another action. Repeating an ineffective input is not evidence of progress."
            ]
        return "\n".join(lines)


def append_history(
    history: deque[tuple[str, str]], frame: str, action: Action, coalesce: bool = True
) -> None:
    if coalesce and history and action.is_noop and history[-1][1] == action.history_text:
        previous = visual(__import__("base64").b64decode(history[-1][0]))
        current = visual(__import__("base64").b64decode(frame))
        if sum(abs(x - y) for x, y in zip(previous, current)) / len(previous) < 2:
            history[-1] = (frame, action.history_text)
            return
    history.append((frame, action.history_text))
