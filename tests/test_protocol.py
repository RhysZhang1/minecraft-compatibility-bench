# SPDX-License-Identifier: GPL-3.0-or-later
"""Protocol compatibility checks; no GPU or game required."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gamescaling.action import parse_action
from jinja2 import Environment

from mcbench.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        profile = {
            "minecraft_version": "1.20.1",
            "world_id": "fixture",
            "initial_goal": "Observe",
            "memory_directory": "memory",
            "episodes_directory": "episodes",
            "control_file": "control.json",
        }
        self.runtime = Runtime(Path(self.directory.name), profile)
        self.monitor = self.runtime.prompt
        self.patch = patch.object(
            self.runtime.memory, "prompt_context", return_value="persistent notes fixture"
        )
        self.rules = patch("mcbench.instance_config.pack_rules", return_value="")
        self.patch.start()
        self.rules.start()

    def tearDown(self):
        self.patch.stop()
        self.rules.stop()
        self.directory.cleanup()

    def test_prompt_matches_official_template(self):
        path = ROOT / "tests/fixtures/protocol/chat_template.jinja"
        marker = "<__test_media__>"
        action = "<|action_start|>0 0 0 ; W ; ; ; ; ; <|action_end|>"
        self.runtime.history.append(("old-image", action))
        actual = self.monitor.make_prompt("new-image", marker)
        messages = [
            {"role": "system", "content": self.monitor.system_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "current game screen"},
                    {"type": "image_url", "image_url": {"url": "old-image"}},
                ],
            },
            {"role": "assistant", "content": action},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.monitor.observation_text()},
                    {"type": "image_url", "image_url": {"url": "new-image"}},
                ],
            },
        ]
        official = (
            Environment()
            .from_string(path.read_text())
            .render(messages=messages, add_generation_prompt=True)
        )
        expected = (
            official.replace("<|vision_start|><|image_pad|><|vision_end|>", marker) + "<think>"
        )
        self.assertEqual(actual["prompt_string"], expected)
        self.assertEqual(actual["multimodal_data"], ["old-image", "new-image"])

    def test_unterminated_generation_does_not_become_action(self):
        partial = "<think>\n\n</think>\n\n<|action_start|>0 0 0 ; W ; W ; W ; W ; W ; W"
        self.assertFalse(parse_action(partial).parsed)
        self.assertTrue(parse_action(partial + "<|action_end|>").parsed)

    def test_thought_quoted_action_is_not_executed(self):
        raw = "<think>format: <|action_start|>0 0 0 ; W ; W ; W ; W ; W ; W<|action_end|>"
        self.assertFalse(parse_action(raw).parsed)


if __name__ == "__main__":
    unittest.main()
