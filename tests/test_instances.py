# SPDX-License-Identifier: GPL-3.0-or-later
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcbench import instance_config as ic
from mcbench.memory import WorldMemory
from mcbench.tools import launch_game

ROOT = Path(__file__).resolve().parents[1]


PATHS = {
    "JAVA_BIN": "java",
    "CLIENT_DIRECTORY": "client",
    "SERVER_DIRECTORY": "server",
    "LIBRARIES_ROOT": "libraries",
}


class InstanceTests(unittest.TestCase):
    def test_worlds_do_not_share_default_memory_or_episodes(self):
        g = ic.template("vanilla-1-20-1", PATHS)
        v = ic.template("vanilla-1-7-10", PATHS)
        self.assertNotEqual(g["memory_directory"], v["memory_directory"])
        self.assertNotEqual(g["episodes_directory"], v["episodes_directory"])
        self.assertNotEqual(g["world_id"], v["world_id"])
        with patch.object(ic, "config", return_value=v):
            self.assertEqual(ic.pack_rules(), "")

    def test_unsupported_version_is_rejected_before_launch(self):
        settings = {
            "selected": "fake",
            "instances": {
                "fake": {
                    **ic.template("vanilla-1-7-10", PATHS),
                    "minecraft_version": "26.3",
                    "backend": "forge1710-lwjgl3ify",
                }
            },
        }
        with patch.object(ic, "settings", return_value=settings):
            with self.assertRaisesRegex(ValueError, "输入后端"):
                ic.config("fake")

    def test_memory_rejects_accidental_world_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "config").mkdir()
            (root / "config/prompt.default.md").write_text("Generic instructions")
            folder = root / "notes"
            a = WorldMemory(root, folder, "world-a")
            a.ensure("test")
            b = WorldMemory(root, folder, "world-b")
            with self.assertRaisesRegex(ValueError, "world|世界"):
                b.ensure("test")

    def test_manifest_inherits_parent_and_keeps_child_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "versions/base"
            p.mkdir(parents=True)
            (p / "base.json").write_text(
                json.dumps(
                    {
                        "id": "base",
                        "mainClass": "Base",
                        "libraries": [{"name": "parent:lib:1"}],
                        "arguments": {"game": ["--a"], "jvm": ["-Da=1"]},
                    }
                )
            )
            child = root / "child.json"
            child.write_text(
                json.dumps(
                    {
                        "id": "child",
                        "inheritsFrom": "base",
                        "mainClass": "Child",
                        "libraries": [],
                        "arguments": {"game": ["--b"]},
                    }
                )
            )
            value = launch_game.manifest(child, source=root)
            self.assertEqual(value["mainClass"], "Child")
            self.assertEqual(value["arguments"]["game"], ["--a", "--b"])
            self.assertEqual(len(value["libraries"]), 1)


if __name__ == "__main__":
    unittest.main()
