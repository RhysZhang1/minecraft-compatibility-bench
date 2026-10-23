# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed entry points preserve lifecycle flag/value ordering."""

import sys
import unittest
from unittest.mock import patch

from mcbench.cli import main


class CliTests(unittest.TestCase):
    def test_lifecycle_options_keep_original_order(self):
        expected = ["mcbench", "start", "--instance", "example", "--profile", "cpu", "--paused"]

        def execute():
            self.assertEqual(sys.argv, expected)
            return 0

        with (
            patch("mcbench.tools.lifecycle.main", side_effect=execute),
            patch.object(sys, "argv", ["mcbench"]),
            patch("os.chdir"),
        ):
            self.assertEqual(main(expected[1:]), 0)


if __name__ == "__main__":
    unittest.main()
