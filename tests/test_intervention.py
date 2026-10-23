# SPDX-License-Identifier: GPL-3.0-or-later
"""Human control boundaries and playback ordering, without GPU, X11 or a server."""

import io
import json
import tempfile
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

from mcbench.feedback import Observation
from mcbench.http import Handler
from mcbench.intervention import InterventionBusy, ManualPlayback, build_plan
from mcbench.runtime import Runtime


class Target:
    def __init__(self):
        self.events = []
        self.held = set()

    def apply(self, keys):
        self.held = keys
        self.events.append(("keys", sorted(keys)))

    def point(self, x, y):
        self.events.append(("point", x, y))

    def move(self, dx, dy, scroll):
        self.events.append(("motion", dx, dy, scroll))


class PlaybackTests(unittest.TestCase):
    def test_drag_moves_only_after_press_then_releases(self):
        plan = build_plan({"kind": "drag", "point": [0.1, 0.2], "end": [0.8, 0.6], "shift": True})
        target = Target()
        player = ManualPlayback(plan, 1000, "session", "Inventory")
        state = {"session": "session", "screen": "Inventory"}
        result = None
        for now in range(1000, 1600, 10):
            result = player.tick(now, target, state, True) or result
        self.assertFalse(result["cancelled"])
        press = target.events.index(("keys", ["LB", "Shift"]))
        points = [i for i, event in enumerate(target.events) if event[0] == "point"]
        self.assertLess(points[0], press)
        self.assertTrue(all(index > press for index in points[1:]))
        self.assertIn(("point", 0.8, 0.6), target.events)
        self.assertEqual(target.held, set())

    def test_cancel_session_screen_and_watchdog_release_without_new_input(self):
        plan = build_plan({"kind": "key", "keys": ["W"], "duration_ms": 2000})
        for reason, now, state, valid in [
            ("control", 1100, {"session": "s", "screen": ""}, False),
            ("session", 1100, {"session": "other", "screen": ""}, True),
            ("screen", 1100, {"session": "s", "screen": "Inventory"}, True),
            ("deadline", 5001, {"session": "s", "screen": ""}, True),
        ]:
            with self.subTest(reason=reason):
                target = Target()
                target.held = {"W"}
                player = ManualPlayback(plan, 1000, "s", "")
                self.assertTrue(player.tick(now, target, state, valid)["cancelled"])
                self.assertEqual(target.events, [("keys", [])])

    def test_inputs_reject_unbounded_or_nonfinite_values(self):
        invalid = [
            {"kind": "key", "keys": ["W"], "duration_ms": 2001},
            {"kind": "key", "keys": ["unknown"]},
            {"kind": "key", "keys": ["W"], "duration_ms": True},
            {"kind": "click", "point": [float("nan"), 0]},
            {"kind": "click", "point": [True, 0]},
            {"kind": "click", "point": [10**1000, 0]},
            {"kind": "drag", "point": [0, 0], "end": [2, 0]},
            {"kind": "look", "mouse": [float("inf"), 0]},
            {"kind": "look", "mouse": [10**1000, 0]},
            {"kind": "scroll", "delta": 0},
            {"kind": "shell", "command": "anything"},
        ]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                build_plan(body)


class InterventionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runtime = Runtime(
            root,
            {
                "backend": "virtual-x11",
                "initial_goal": "Observe",
                "world_id": "test",
                "control_file": "control.json",
                "episodes_directory": "episodes",
                "memory_directory": "memory",
            },
        )
        self.runtime.bridge.mkdir(parents=True)
        (root / "logs").mkdir()
        self.game = {
            "connected": True,
            "timestamp": int(time.time() * 1000),
            "session": "session",
            "screen": "Inventory",
            "screen_known": True,
            "capabilities": {"manual_input": True},
        }
        (self.runtime.bridge / "state.json").write_text(json.dumps(self.game))
        self.body = {
            "kind": "click",
            "point": [0.5, 0.5],
            "session": "session",
            "screen": "Inventory",
        }

    def test_manual_action_invalidates_model_and_records_separate_origin(self):
        def publish(path, value):
            path = Path(path)
            path.write_text(json.dumps(value))
            if path.name == "command.json":
                (path.parent / "completed.json").write_text(
                    json.dumps(
                        {
                            "id": value["id"],
                            "time": int(time.time() * 1000),
                            "cancelled": False,
                            "source": "human",
                        }
                    )
                )

        self.runtime.history.append(("old", "action"))
        epoch = self.runtime.control_epoch
        before = Observation(b"fixture", {}, self.game)
        with (
            patch("mcbench.intervention.atomic", side_effect=publish),
            patch("mcbench.intervention.read_observation", return_value=before),
            patch.object(self.runtime.memory, "checkpoint"),
        ):
            result = self.runtime.intervention.run(self.body)
        self.assertTrue(result["executed"])
        self.assertEqual(result["source"], "human")
        self.assertFalse(self.runtime.state["enabled"])
        self.assertEqual(self.runtime.state["step"], 0)
        self.assertFalse(self.runtime.history)
        self.assertGreater(self.runtime.control_epoch, epoch)
        self.assertTrue(list((self.runtime.root / "interventions").glob("*.json")))
        self.assertFalse(list(self.runtime.episodes.glob("*.json")))

    def test_stale_ui_cannot_send_to_another_session(self):
        with self.assertRaisesRegex(ValueError, "界面已变化"):
            self.runtime.intervention.run({**self.body, "session": "stale"})
        self.assertFalse((self.runtime.bridge / "command.json").exists())
        self.assertFalse(self.runtime.intervention.active)

    def test_emergency_release_does_not_wait_for_busy_channel(self):
        epoch = self.runtime.control_epoch
        with self.runtime.command_lock:
            with self.assertRaises(InterventionBusy):
                self.runtime.intervention.run(self.body)
            self.assertTrue(self.runtime.intervention.run({"kind": "release"})["released"])
        self.assertGreater(self.runtime.control_epoch, epoch)
        self.assertFalse(self.runtime.state["enabled"])

    def test_failed_control_write_does_not_lock_future_interventions(self):
        with patch("mcbench.intervention.atomic", side_effect=OSError("read only")):
            with self.assertRaises(OSError):
                self.runtime.intervention.run(self.body)
        self.assertFalse(self.runtime.intervention.active)
        self.assertTrue(self.runtime.command_lock.acquire(blocking=False))
        self.runtime.command_lock.release()

    def test_legacy_capability_list_is_reported_as_unsupported(self):
        (self.runtime.bridge / "state.json").write_text(json.dumps({"capabilities": ["frames"]}))
        self.assertFalse(self.runtime.intervention.status()["supported"])

    def test_http_cannot_resume_model_during_manual_action(self):
        handler = object.__new__(Handler)
        handler.runtime = self.runtime
        handler.path = "/api/control"
        handler.headers = Message()
        for key, value in {
            "Host": "127.0.0.1:8790",
            "Content-Type": "application/json",
            "Content-Length": "16",
        }.items():
            handler.headers[key] = value
        handler.rfile = io.BytesIO(b'{"enabled":true}')
        handler.json_response = Mock()
        self.runtime.intervention.active = True
        self.runtime.state["enabled"] = False
        handler.do_POST()
        self.assertEqual(handler.json_response.call_args.args[0], 409)
        self.assertFalse(self.runtime.state["enabled"])


if __name__ == "__main__":
    unittest.main()
