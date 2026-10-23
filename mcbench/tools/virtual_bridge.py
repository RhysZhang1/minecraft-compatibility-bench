# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared pixel/action backend for vanilla and modded clients in a private display."""

import json
import signal
import threading
import time
import uuid

from PIL import ImageDraw

from mcbench import instance_config as ic
from mcbench import server_console as server_console
from mcbench.paths import ROOT
from mcbench.virtual_x11 import Session

BRIDGE = ROOT / "runtime/bridge"
STOP = threading.Event()
ONLINE = False


def read(name):
    try:
        return json.loads((BRIDGE / name).read_text())
    except (OSError, ValueError):
        return {}


def write(name, value):
    p = BRIDGE / name
    tmp = p.with_suffix(".virtual.tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(p)


def online():
    global ONLINE
    while not STOP.is_set():
        try:
            ONLINE = (
                ic.config()["player"] in server_console.execute("list")
                if ic.console_enabled()
                else False
            )
        except (OSError, ValueError, ConnectionError):
            ONLINE = False
        STOP.wait(1)


def lease(epoch):
    safety = read("safety.json")
    return (
        epoch is not None
        and safety.get("epoch") == epoch
        and 0 <= time.time() * 1000 - safety.get("timestamp", 0) < 1500
    )


def main():
    from mcbench.tools import manage

    BRIDGE.mkdir(parents=True, exist_ok=True)
    session = (read("session.json").get("session") if manage.owned("client") else None) or str(
        uuid.uuid4()
    )
    write("session.json", {"session": session})
    signal.signal(signal.SIGTERM, lambda *args: STOP.set())
    signal.signal(signal.SIGINT, lambda *args: STOP.set())
    x = Session()
    ident = read("command.json").get("id", -1)
    action = None
    start = 0
    frame_id = 0
    last_frame = 0
    last_state = 0
    last_find = 0
    last_error = ""
    mining = None
    last_screen = None
    prime = None
    pointer_ready_at = 0
    threading.Thread(target=online, daemon=True).start()
    from mcbench.game_config import config

    fps = max(1, min(30, config()["client"].get("preview_fps", 20)))
    capture_count = 0
    capture_since = time.monotonic()
    capture_fps = 0
    try:
        while not STOP.is_set():
            now = time.time() * 1000
            sensor = read("sensors.json")
            if sensor.get("session") != session or now - sensor.get("timestamp", 0) > 1500:
                sensor = {}
            screen = sensor.get("screen", "")
            target = sensor.get("target_block")
            if mining and (
                not lease(mining["epoch"])
                or now >= mining["deadline"]
                or screen
                or (mining["target"] and target != mining["target"])
            ):
                x.apply(set())
                mining = None
            if time.monotonic() - last_find > 1:
                x.find()
                last_find = time.monotonic()
            if x.window and screen != last_screen:
                last_screen = screen
                x.move(1000 / x.width, 0, 0)
                prime = now + 25
                pointer_ready_at = now + 60
            if prime and now >= prime:
                x.move(-1000 / x.width, 0, 0)
                prime = None
            x.ei.gs_pump()
            value = read("command.json")
            if now >= pointer_ready_at and not action and value.get("id", -1) > ident:
                ident = value["id"]
                previous = mining
                continuation = bool(
                    previous
                    and previous["target"] == target
                    and not screen
                    and value.get("sustain_mining")
                    and all(
                        "LB" in s and not any(k in s for k in ["RB", "MB", "E", "Esc"])
                        for s in value.get("steps", [])
                    )
                )
                if not continuation:
                    x.apply(set())
                mining = None
                start = now
                action = dict(value)
                action["_hold_started"] = previous["started"] if continuation else now
                action["_continuation"] = continuation
                if lease(action.get("epoch")) and x.window:
                    x.move(*action.get("mouse", [0, 0, 0]))
            if action:
                cancelled = (
                    not lease(action.get("epoch"))
                    or not x.window
                    or (action.get("_continuation") and now - action["_hold_started"] >= 10000)
                )
                elapsed = now - start
                if cancelled or elapsed >= 200:
                    keep = (
                        not cancelled
                        and not screen
                        and action.get("sustain_mining")
                        and target
                        and all(
                            "LB" in s and not any(k in s for k in ["RB", "MB", "E", "Esc"])
                            for s in action.get("steps", [])
                        )
                    )
                    x.apply({"LB"} if keep else set())
                    if keep:
                        mining = {
                            "epoch": action["epoch"],
                            "target": target,
                            "deadline": action["_hold_started"] + 10000,
                            "started": action["_hold_started"],
                        }
                    write(
                        "completed.json",
                        {
                            "id": ident,
                            "time": now,
                            "session": session,
                            "cancelled": cancelled,
                            "mining_active": bool(mining),
                        },
                    )
                    action = None
                else:
                    step = min(5, int(elapsed / 33.333))
                    x.apply(action.get("steps", [[]] * 6)[step])
            if now - last_frame >= 1000 / fps and x.window:
                try:
                    im = x.capture()
                    cursor = x.cursor()
                    if screen:
                        # Cursor belongs to the virtual display, visible in preview and model input.
                        draw = ImageDraw.Draw(im)
                        cx, cy = cursor["x"], cursor["y"]
                        draw.line((cx - 9, cy, cx + 9, cy), fill="black", width=5)
                        draw.line((cx, cy - 9, cx, cy + 9), fill="black", width=5)
                        draw.line((cx - 8, cy, cx + 8, cy), fill="white", width=2)
                        draw.line((cx, cy - 8, cx, cy + 8), fill="white", width=2)
                    tmp = BRIDGE / "frame.virtual.jpg"
                    im.save(tmp, "JPEG", quality=82)
                    tmp.replace(BRIDGE / "frame.jpg")
                    frame_id += 1
                    last_frame = now
                    capture_count += 1
                    write(
                        "frame-meta.json",
                        {
                            "schema_version": 2,
                            "session": session,
                            "frame_id": frame_id,
                            "captured_at": now,
                            "command_id": ident,
                            "image_mtime_ms": (BRIDGE / "frame.jpg").stat().st_mtime_ns // 1000000,
                        },
                    )
                    last_error = ""
                except (OSError, ValueError, ConnectionError) as exc:
                    last_error = str(exc)
            if time.monotonic() - capture_since >= 2:
                capture_fps = round(capture_count / (time.monotonic() - capture_since), 1)
                capture_count = 0
                capture_since = time.monotonic()
            if now - last_state >= 50:
                state = {
                    **sensor,
                    "schema_version": 2,
                    "session": session,
                    "timestamp": now,
                    "backend": "virtual-x11",
                    "instance": ic.selected(),
                    "connected": bool(
                        (ONLINE or sensor.get("world_loaded")) and x.window and frame_id > 10
                    ),
                    "input_isolated": True,
                    "display_isolated": True,
                    "window_visible": False,
                    "virtual_window_visible": bool(x.window),
                    "physical_focused": False,
                    "cursor_free": True,
                    "cursor": x.cursor() if x.window else {},
                    "screen": screen,
                    "screen_known": "screen" in sensor,
                    "command_id": ident,
                    "busy": bool(action),
                    "mining_active": bool(mining),
                    "left_button_down": "LB" in x.held,
                    "held_keys": sorted(x.held),
                    "capture_fps": capture_fps,
                    "error": last_error,
                    "capabilities": {
                        "frames": True,
                        "isolated_input": True,
                        "gui": True,
                        "inventory": bool(sensor.get("inventory") is not None),
                        "block_target": bool(sensor),
                        "mining_hold": bool(sensor),
                    },
                }
                write("state.json", state)
                last_state = now
            STOP.wait(0.008)
    finally:
        x.apply(set())
        write(
            "state.json",
            {
                "timestamp": time.time() * 1000,
                "connected": False,
                "session": session,
                "backend": "virtual-x11",
            },
        )


if __name__ == "__main__":
    main()
