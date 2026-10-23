# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt responsibilities for the local compatibility bench."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from gamescaling.prompt import build_system_prompt

from mcbench import instance_config
from mcbench.io_utils import readjson

if TYPE_CHECKING:
    from mcbench.runtime import Runtime


class PromptBuilder:
    """Format the checkpoint protocol; state is supplied by the runtime."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def system_prompt(self) -> str:
        return build_system_prompt(
            "Minecraft " + self.runtime.instance["minecraft_version"],
            rules="Avoid destroying player buildings. Do not type chat commands. Each action packet covers 200ms. Movement and use keys release afterwards. To mine, aim steadily at a harvestable block and hold LB in all six substeps. Only LB can then remain held on that same block while you infer, for at most 10 seconds. The mining hold stops if the target changes, the block breaks, a GUI opens, control pauses, or the watchdog expires. Check the next observation for results. Only act on the current screenshot. Verify what the previous action actually changed. "
            + instance_config.pack_rules(self.runtime.instance),
            key_bindings=[
                ("W", "Move forward"),
                ("A", "Strafe left"),
                ("S", "Move backward"),
                ("D", "Strafe right"),
                ("Space", "Jump"),
                ("Shift", "Sneak"),
                ("Ctrl", "Sprint"),
                ("LB", "Attack / mine"),
                ("RB", "Use / place / interact"),
                ("E", "Open or close inventory"),
                ("Esc", "Close current screen"),
                ("Q", "Drop item"),
                *[
                    (n, "Select hotbar slot " + str(i))
                    for i, n in enumerate(
                        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"], 1
                    )
                ],
            ],
            mouse_aim=True,
        )

    def observation_text(self, memory_context: str | None = None, feedback: str = "") -> str:
        if memory_context is None:
            memory_context = self.runtime.memory.prompt_context()
        return (
            "current game screen\nCurrent objective: "
            + self.runtime.state["goal"]
            + "\n"
            + memory_context
            + ("\n" + feedback if feedback else "")
        )

    def make_prompt(
        self,
        frame: str,
        marker: str | None = None,
        memory_context: str | None = None,
        feedback: str = "",
    ) -> dict[str, Any]:
        if marker is None:
            identity = readjson(self.runtime.root / "runtime/model-active.json").get("time")
            if self.runtime.marker_cache.get(
                "identity"
            ) != identity or not self.runtime.marker_cache.get("marker"):
                with self.runtime.request("/props", timeout=5) as response:
                    self.runtime.marker_cache.update(
                        identity=identity, marker=json.load(response)["media_marker"]
                    )
            marker = self.runtime.marker_cache["marker"]
        prompt = "<|im_start|>system\n" + self.system_prompt() + "<|im_end|>\n"
        images = []
        with self.runtime.lock:
            history = tuple(self.runtime.history)
        for old, action in history:
            prompt += "<|im_start|>user\ncurrent game screen" + marker + "<|im_end|>\n"
            prompt += "<|im_start|>assistant\n<think>\n\n</think>\n\n" + action + "<|im_end|>\n"
            images.append(old)
        prompt += (
            "<|im_start|>user\n"
            + self.observation_text(memory_context, feedback)
            + marker
            + "<|im_end|>\n<|im_start|>assistant\n<think>"
        )
        images.append(frame)
        return {"prompt_string": prompt, "multimodal_data": images}
