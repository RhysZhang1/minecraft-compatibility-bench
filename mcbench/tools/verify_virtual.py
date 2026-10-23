# SPDX-License-Identifier: GPL-3.0-or-later
"""Live generic acceptance: real movement, GUI, held mining and pause release."""

import json
import shutil
import time
import urllib.request

from mcbench import instance_config as ic
from mcbench import server_console as server_console
from mcbench.paths import ROOT
from mcbench.tools.verify_input import read, until, write

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def control(enabled):
    req = urllib.request.Request(
        "http://127.0.0.1:8790/api/control",
        data=json.dumps({"enabled": enabled}).encode(),
        headers={"Content-Type": "application/json"},
    )
    OPENER.open(req).close()


def packet(keys=None, mouse=None, sustain=False):
    ident = max(int(time.time() * 1000), read("state.json").get("command_id", 0) + 1)
    write(
        "command.json",
        {
            "id": ident,
            "epoch": read("safety.json")["epoch"],
            "steps": keys or [[]] * 6,
            "mouse": mouse or [0, 0, 0],
            "sustain_mining": sustain,
        },
    )
    complete = until(lambda: (v := read("completed.json")).get("id") == ident and v)
    assert not complete.get("cancelled"), complete
    time.sleep(0.15)
    return read("state.json")


def fill(x1, y1, z1, x2, y2, z2, block):
    if ic.config()["minecraft_version"] == "1.7.10":
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                for z in range(z1, z2 + 1):
                    server_console.execute(f"setblock {x} {y} {z} {block}")
    else:
        server_console.execute(f"fill {x1} {y1} {z1} {x2} {y2} {z2} {block}")


def teleport(player, x, y, z, yaw, pitch):
    if ic.config()["minecraft_version"] != "1.7.10":
        server_console.execute("tp " + player + " " + f"{x} {y} {z} {yaw} {pitch}")
        return
    server_console.execute("tp " + player + " " + f"{x} {y} {z}")
    time.sleep(0.4)
    for _ in range(40):
        state = read("state.json")
        dyaw = (yaw - state["yaw"] + 180) % 360 - 180
        dpitch = pitch - state["pitch"]
        if abs(dyaw) < 1 and abs(dpitch) < 1:
            return
        dx = max(-100, min(100, dyaw / (0.15 * 854) * 1000))
        dy = max(-100, min(100, dpitch / (0.15 * 480) * 1000))
        packet(mouse=[dx, dy, 0])
    raise TimeoutError("旧版测试相机未转到目标角度")


def main():
    control(False)
    time.sleep(0.2)
    before = until(lambda: (s := read("state.json")).get("connected") and s)
    evidence = {"instance": ic.selected(), "before": before, "time": time.time()}
    if before.get("screen"):
        packet([["Esc"]] + [[]] * 5)
    # Use a temporary platform high above normal terrain; restore original player position.
    player = ic.config()["player"]
    telemetry = all(k in before for k in ["x", "y", "z", "yaw", "pitch"])
    try:
        if telemetry:
            fill(-2, 219, -2, 2, 219, 4, "minecraft:stone")
            teleport(player, 0.5, 220, 3.5, 180, 0)
            time.sleep(0.5)
        initial = read("state.json")
        moved = packet([["W"]] * 6, [30, 0, 0])
        evidence["after_move"] = moved
        if telemetry:
            distance = sum((moved[k] - initial[k]) ** 2 for k in ("x", "z")) ** 0.5
            assert distance > 0.1, ("movement", initial, moved)
            assert abs(moved["yaw"] - initial["yaw"]) > 1, ("mouse", initial, moved)
            evidence["distance"] = distance
        inventory = packet([["E"]] + [[]] * 5)
        evidence["inventory_screen"] = inventory
        if telemetry:
            assert inventory.get("screen"), inventory
        packet([[]] * 6, [120, 20, 0])
        shutil.copy2(
            ROOT / "runtime/bridge/frame.jpg", ROOT / "runtime" / ("gui-" + ic.selected() + ".jpg")
        )
        closed = packet([["Esc"]] + [[]] * 5)
        if telemetry:
            assert not closed.get("screen"), closed
        if telemetry:
            server_console.execute("setblock 0 220 0 minecraft:dirt")
            teleport(player, 0.5, 220, 3.5, 180, 20.5)
            time.sleep(0.7)
            aimed = read("state.json")
            assert aimed.get("target_block", {}).get("block") == "minecraft:dirt", aimed
            held = packet([["LB"]] * 6, sustain=True)
            evidence["held_mining"] = held
            assert held.get("mining_active"), held
            broken = until(
                lambda: (
                    (s := read("state.json")).get("target_block", {}).get("block")
                    != "minecraft:dirt"
                    and not s.get("mining_active")
                    and s
                ),
                timeout=10,
            )
            evidence["after_break"] = broken
            teleport(player, 0.5, 220, 0.5, 180, 0)
            time.sleep(1)
            collected = read("state.json")
            assert any(i["item"] == "minecraft:dirt" for i in collected.get("inventory", [])), (
                collected
            )
            evidence["collected"] = collected
            server_console.execute("setblock 0 220 0 minecraft:stone")
            teleport(player, 0.5, 220, 3.5, 180, 20.5)
            time.sleep(0.5)
            packet([["LB"]] * 6, sustain=True)
            control(False)
            released = until(
                lambda: (
                    (s := read("state.json")).get("left_button_down") is False
                    and not s.get("mining_active")
                    and s
                )
            )
            evidence["after_pause"] = released
    finally:
        control(False)
        if telemetry:
            teleport(player, *(before[k] for k in ["x", "y", "z", "yaw", "pitch"]))
            fill(-2, 219, -2, 2, 220, 4, "minecraft:air")
    evidence["passed"] = True
    evidence["scope"] = (
        "Virtual display inputs; movement, GUI, mining where read-only telemetry is available. No human hardware interaction was required."
    )
    folder = ROOT / "runtime/validation"
    folder.mkdir(exist_ok=True)
    target = folder / (ic.selected() + ".json")
    target.write_text(json.dumps(evidence, indent=2))
    print(
        json.dumps(
            {
                "passed": True,
                "instance": ic.selected(),
                "telemetry": telemetry,
                "evidence": str(target),
            }
        )
    )


if __name__ == "__main__":
    main()
