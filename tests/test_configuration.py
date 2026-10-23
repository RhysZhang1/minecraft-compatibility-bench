# SPDX-License-Identifier: GPL-3.0-or-later
"""A fresh checkout must not inherit the author's machine or world selection."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcbench import instance_config as config


class ConfigurationTests(unittest.TestCase):
    def test_clean_templates_are_not_selected_instances(self):
        public = json.loads((config.ROOT / "instance-settings.json").read_text())
        self.assertIsNone(public["selected"])
        self.assertEqual(public["instances"], {})
        self.assertNotIn("hmcl", json.dumps(public).lower())
        self.assertNotIn("/usr/lib/jvm", json.dumps(public))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "instance-settings.json").write_text(json.dumps(public))
            with patch.object(config, "ROOT", root), patch.dict("os.environ", {}, clear=True):
                self.assertIsNone(config.selected())
                with self.assertRaisesRegex(ValueError, "setup.sh"):
                    config.config()

    def test_unfilled_template_has_an_actionable_error(self):
        public = json.loads((config.ROOT / "instance-settings.json").read_text())
        profile = public["templates"]["vanilla-1-20-1"]
        with self.assertRaisesRegex(ValueError, "Unresolved template.*JAVA_BIN"):
            config.validate("example", profile)


if __name__ == "__main__":
    unittest.main()
