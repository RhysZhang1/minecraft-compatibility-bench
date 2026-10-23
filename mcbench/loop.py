# SPDX-License-Identifier: GPL-3.0-or-later
"""Loop responsibilities for the local compatibility bench."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gamescaling.action import ACTION_END, Action, parse_action, split_reasoning

from mcbench.decisions import recovery_decision, should_execute
from mcbench.feedback import Observation, append_history, read_observation
from mcbench.io_utils import atomic, readjson
from mcbench.memory import replace as replace_memory

if TYPE_CHECKING:
    from mcbench.runtime import Runtime


@dataclass(frozen=True)
class Generation:
    """One response, kept separate from permission to execute its action."""

    raw: str
    reasoning: str
    action: Action
    latency: float
    timings: dict[str, Any]


class DecisionLoop:
    """Run one model/action/feedback cycle at a time with cancellation gates."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def summarize_memory(self) -> None:
        with self.runtime.lock:
            goal = self.runtime.state["goal"]
            step = self.runtime.state["step"]
            epoch = self.runtime.control_epoch
        self.runtime.memory.running = True
        self.runtime.state["phase"] = "正在整理续玩笔记；此请求不执行游戏动作"
        raw = ""
        error = ""
        try:
            body = self.runtime.memory.summary_request(
                goal, readjson(self.runtime.bridge / "state.json"), step
            )
            with self.runtime.request("/completion", body, timeout=60) as response:
                reply = json.load(response)
            raw = reply.get("content", "")
            if epoch != self.runtime.control_epoch:
                raise ValueError("整理期间目标或控制状态已变化，本次草稿未采用")
            self.runtime.memory.apply_summary(
                raw,
                step,
                readjson(self.runtime.root / "runtime/model-active.json").get("key", "unknown"),
            )
        except Exception as exc:
            error = str(exc)
            self.runtime.memory.summary_failed(error, step)
        finally:
            replace_memory(
                self.runtime.memory.folder / "summaries" / f"{time.time_ns()}-{step}.json",
                json.dumps(
                    {
                        "time": time.time(),
                        "step": step,
                        "raw": raw,
                        "error": error,
                        "executed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            self.runtime.memory.running = False

    def generate(
        self, frame: str, memory_context: str, feedback_text: str, epoch: int
    ) -> Generation:
        """Stream one checkpoint response and restore only a confirmed stop boundary."""
        t0 = time.monotonic()
        text = ""
        finish = {}
        with self.runtime.request(
            "/completion",
            {
                "prompt": self.runtime.prompt.make_prompt(
                    frame, memory_context=memory_context, feedback=feedback_text
                ),
                "stream": True,
                "temperature": 1.0,
                "top_k": 0,
                "top_p": 1.0,
                "min_p": 0.0,
                "repeat_penalty": 1.0,
                "n_predict": 768,
                "stop": [ACTION_END],
                "cache_prompt": True,
                "return_tokens": True,
            },
            timeout=600,
        ) as resp:
            for line in resp:
                if epoch != self.runtime.control_epoch or self.runtime.abort.is_set():
                    break
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                chunk = json.loads(payload)
                if "error" in chunk:
                    raise RuntimeError(chunk["error"])
                text += chunk.get("content", "")
                self.runtime.state["raw"] = "<think>" + text
                if chunk.get("stop"):
                    finish = chunk
        raw = "<think>" + text
        if (
            ACTION_END not in raw
            and finish.get("stop_type") == "word"
            and (finish.get("stopping_word") == ACTION_END)
        ):
            raw += ACTION_END
        a = parse_action(raw)
        reasoning, _, _ = split_reasoning(raw)
        elapsed = time.monotonic() - t0
        return Generation(raw, reasoning, a, elapsed, finish.get("timings", {}))

    def observe_result(
        self,
        observation: Observation,
        a: Action,
        frame: str,
        completed: dict[str, Any],
        epoch: int,
        episode_id: str,
        record: dict[str, Any],
    ) -> float:
        """Accept a fresh post-ack frame before recording effects or recovery."""
        after = read_observation(
            self.runtime.bridge,
            after=completed["time"],
            timeout=self.runtime.control_settings["fresh_frame_timeout_seconds"],
            cancel=lambda: self.runtime.abort.is_set() or epoch != self.runtime.control_epoch,
        )
        (self.runtime.episodes / (episode_id + ".after.jpg")).write_bytes(after.image)
        record["game_after"] = after.game
        record["after_observation"] = after.metadata
        result = self.runtime.feedback.record(observation, after, a)
        record["feedback"] = result
        self.runtime.state["feedback"] = result
        with self.runtime.lock:
            append_history(
                self.runtime.history,
                frame,
                a,
                self.runtime.control_settings.get("coalesce_identical_idle_history", True),
            )
            decision = recovery_decision(self.runtime.feedback)
            if decision.reset_history:
                latest = self.runtime.history[-1] if self.runtime.history else None
                self.runtime.history.clear()
                if latest:
                    self.runtime.history.append(latest)
                self.runtime.state["recovery_reason"] = (
                    "连续无明显变化，重新观察；没有替模型点击按钮"
                )
            if decision.pause:
                self.runtime.state["enabled"] = False
                self.runtime.control_epoch += 1
                self.runtime.publish_safety()
                self.runtime.state["recovery_reason"] = (
                    "有限次数重新观察后仍无明显变化，保留现场并暂停"
                )
                atomic(
                    self.runtime.control_file,
                    {"enabled": False, "goal": self.runtime.state["goal"]},
                )
        return after.metadata["captured_at"]

    def loop(self) -> None:
        command_id = int(time.time() * 1000)
        last_frame_time = 0
        while not self.runtime.abort.is_set():
            record = None
            stamp = None
            cycle_started = time.monotonic()
            try:
                with self.runtime.lock:
                    enabled = self.runtime.state["enabled"]
                    epoch = self.runtime.control_epoch
                game = readjson(self.runtime.bridge / "state.json")
                if time.monotonic() - self.runtime.memory.last_checkpoint > 2:
                    self.runtime.memory.checkpoint(
                        self.runtime.state["goal"], game, self.runtime.state["step"]
                    )
                if self.runtime.memory.due(self.runtime.state["step"]) and (
                    self.runtime.memory.pending or enabled
                ):
                    self.summarize_memory()
                if not enabled:
                    self.runtime.state["phase"] = "已暂停；已请求释放动作与挖掘长按"
                    self.runtime.abort.wait(self.runtime.control_settings["idle_wait_seconds"])
                    continue
                if (
                    not game.get("connected")
                    or time.time() * 1000 - game.get("timestamp", 0) > 3000
                ):
                    self.runtime.state["phase"] = "等待 Minecraft 客户端连接配置的服务器"
                    self.runtime.abort.wait(self.runtime.control_settings["idle_wait_seconds"])
                    continue
                if self.runtime.services.memory().get("available_gb", 100) < 1.5:
                    self.runtime.state["phase"] = "可用内存低于1.5GiB，等待资源恢复"
                    self.runtime.abort.wait(0.5)
                    continue
                cycle_started = time.monotonic()
                observation = read_observation(
                    self.runtime.bridge,
                    after=last_frame_time,
                    timeout=self.runtime.control_settings["fresh_frame_timeout_seconds"],
                    cancel=lambda: (
                        self.runtime.abort.is_set() or epoch != self.runtime.control_epoch
                    ),
                )
                game = observation.game
                frame_bytes = observation.image
                frame = base64.b64encode(frame_bytes).decode()
                stamp = f"{self.runtime.state['step'] + 1:06d}"
                self.runtime.episodes.mkdir(parents=True, exist_ok=True)
                (self.runtime.episodes / (stamp + ".jpg")).write_bytes(frame_bytes)
                self.runtime.state.update(
                    phase="模型正在观察并生成动作",
                    raw="",
                    thinking="",
                    inference_started=time.time(),
                )
                memory_context = self.runtime.memory.prompt_context()
                feedback_text = self.runtime.feedback.text(game)
                generation = self.generate(frame, memory_context, feedback_text, epoch)
                raw, reasoning, a, elapsed = (
                    generation.raw,
                    generation.reasoning,
                    generation.action,
                    generation.latency,
                )
                self.runtime.state.update(
                    raw=raw,
                    thinking=reasoning,
                    latency=elapsed,
                    step=self.runtime.state["step"] + 1,
                    parsed=self.runtime.state["parsed"] + int(a.parsed),
                    last_action=a.history_text,
                    inference_started=None,
                )
                record = {
                    "timestamp": time.time(),
                    "step": self.runtime.state["step"],
                    "raw": raw,
                    "reasoning": reasoning,
                    "action": a.history_text,
                    "parsed": a.parsed,
                    "latency": elapsed,
                    "game_before": game,
                    "observation": observation.metadata,
                    "timings": generation.timings,
                    "executed": False,
                    "instance": self.runtime.instance["key"],
                    "model": readjson(self.runtime.root / "runtime/model-active.json"),
                    "continuation_memory": {
                        "revision": self.runtime.memory.config()["revision"],
                        "context": memory_context,
                        "sha256": hashlib.sha256(memory_context.encode()).hexdigest(),
                    },
                    "feedback_input": feedback_text,
                }
                current = readjson(self.runtime.bridge / "state.json")
                with self.runtime.lock:
                    # Cancellation or reconnection invalidates an otherwise valid packet.
                    valid_session = current.get("session") == game.get("session") and current.get(
                        "connected"
                    )
                    execute_action = should_execute(
                        a,
                        enabled=self.runtime.state["enabled"],
                        epoch_matches=epoch == self.runtime.control_epoch,
                        session_matches=valid_session,
                    )
                    if execute_action:
                        command_id = max(
                            command_id + 1,
                            int(time.time() * 1000),
                            current.get("command_id", 0) + 1,
                        )
                        atomic(
                            self.runtime.bridge / "command.json",
                            {
                                "id": command_id,
                                "mouse": a.mouse,
                                "steps": a.steps,
                                "epoch": epoch,
                                "sustain_mining": True,
                            },
                        )
                if execute_action:
                    self.runtime.state["phase"] = "客户端执行动作并检查结果"
                    deadline = time.monotonic() + 10
                    completed = {}
                    while time.monotonic() < deadline:
                        # File publication is asynchronous; match the exact command ID.
                        completed = readjson(self.runtime.bridge / "completed.json")
                        if completed.get("id") == command_id:
                            break
                        if self.runtime.abort.wait(0.015):
                            break
                    else:
                        raise RuntimeError("客户端没有确认动作完成；停止发送后续动作")
                    record.update(
                        executed=completed.get("id") == command_id
                        and (not completed.get("cancelled", False)),
                        completion=completed,
                        command_id=command_id,
                    )
                    if record["executed"] and epoch == self.runtime.control_epoch:
                        last_frame_time = self.observe_result(
                            observation, a, frame, completed, epoch, stamp, record
                        )
                    else:
                        record["discard_reason"] = "客户端取消动作或控制状态已变化"
                elif epoch != self.runtime.control_epoch or not valid_session:
                    record["discard_reason"] = "控制状态或客户端连接已变化"
                elif not a.parsed:
                    self.runtime.state["errors"] += 1
                    self.runtime.state["phase"] = "输出未通过解析，保留原文并重新观察"
                    self.runtime.history.clear()
                record["cycle_seconds"] = time.monotonic() - cycle_started
                atomic(self.runtime.episodes / (stamp + ".json"), record)
                self.runtime.event("decision", **record)
            except InterruptedError:
                self.runtime.state["inference_started"] = None
                if record:
                    record.update(
                        discard_reason="等待新画面期间控制状态已变化",
                        cycle_seconds=time.monotonic() - cycle_started,
                    )
                    atomic(self.runtime.episodes / (stamp + ".json"), record)
                    self.runtime.event("decision", **record)
            except Exception as exc:
                with self.runtime.lock:
                    self.runtime.control_epoch += 1
                    self.runtime.publish_safety()
                self.runtime.state["errors"] += 1
                self.runtime.state.update(phase="等待恢复：" + str(exc), inference_started=None)
                if record:
                    record.update(
                        observation_error=str(exc), cycle_seconds=time.monotonic() - cycle_started
                    )
                    atomic(self.runtime.episodes / (stamp + ".json"), record)
                    self.runtime.event("decision", **record)
                self.runtime.event("error", message=str(exc))
                traceback.print_exc()
                self.runtime.history.clear()
                self.runtime.marker_cache.clear()
                self.runtime.abort.wait(0.5)
