# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen real-frame regressions, with explicit authored boundary cases."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mcbench.replay import replay_file

FIXTURE = Path(__file__).parent / "fixtures/golden/replay.json"


class ReplayTests(unittest.TestCase):
    def test_all_frozen_cases(self):
        report = replay_file(FIXTURE)
        self.assertTrue(report["passed"], json.dumps(report["failures"], indent=2))
        self.assertGreater(report["checks"], 250)

    def test_regression_is_detected_without_rewriting_expectations(self):
        source = json.loads(FIXTURE.read_text())
        source["sequences"] = [source["sequences"][0]]
        source["sequences"][0]["cases"] = [source["sequences"][0]["cases"][0]]
        case = source["sequences"][0]["cases"][0]
        case["expected"]["action"]["mouse"][0] += 1
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for frame in ("before", "after"):
                name = case[frame]["frame"]
                (target / name).write_bytes((FIXTURE.parent / name).read_bytes())
            path = target / "mutated.json"
            path.write_text(json.dumps(source))
            before = path.read_bytes()
            self.assertFalse(replay_file(path)["passed"])
            self.assertEqual(path.read_bytes(), before)

    def test_import_does_not_open_a_workspace_or_graphical_session(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "MCBENCH_WORKSPACE": folder, "DISPLAY": "", "WAYLAND_DISPLAY": ""}
            result = subprocess.run(
                [sys.executable, "-c", "import mcbench.runtime, mcbench.replay; print('ready')"],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.stdout.strip(), "ready")
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
