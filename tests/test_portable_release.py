# SPDX-License-Identifier: GPL-3.0-or-later
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcbench.tools import backup, legacy_bindings, manage, restore_private, virtual_display

ROOT = Path(__file__).resolve().parents[1]


class PortableTests(unittest.TestCase):
    def test_editable_package_finder_rebinds_paths_with_quotes(self):
        with tempfile.TemporaryDirectory() as folder:
            venv = Path(folder)
            finder = (
                venv
                / "lib/python3.11/site-packages/__editable___minecraft_compatibility_bench_0_3_0_finder.py"
            )
            finder.parent.mkdir(parents=True)
            finder.write_text(
                "MAPPING = {'mcbench': '/old/work/mcbench', 'gamescaling': '/old/work/vendor/GameScaling/gamescaling'}\n"
            )
            target = "/new/user's work"
            restore_private.rebind_editable_install(venv, {"/old/work": target}, "/old")
            namespace = {}
            exec(compile(finder.read_text(), str(finder), "exec"), namespace)
            self.assertEqual(namespace["MAPPING"]["mcbench"], target + "/mcbench")
            self.assertEqual(
                namespace["MAPPING"]["gamescaling"], target + "/vendor/GameScaling/gamescaling"
            )

    def test_restore_rebinds_external_java_and_tilde_libraries(self):
        metadata = {
            "workspace": "/home/old/work",
            "home": "/home/old",
            "external_exports": {
                "external/java/modern": "/usr/lib/jvm/java-21",
                "external/libraries/gtnh/libraries": "/home/old/.config/hmcl/.minecraft/libraries",
                "external/libraries/gtnh/assets": "/home/old/.config/hmcl/.minecraft/assets",
            },
        }
        mapping = restore_private.path_mapping(metadata, Path("/tmp/restored"))
        profile = {
            "libraries_root": "~/.config/hmcl/.minecraft",
            "java": "/usr/lib/jvm/java-21/bin/java",
            "notes": "ordinary user notes",
        }
        actual = restore_private.convert_paths(profile, mapping, metadata["home"])
        self.assertEqual(
            actual,
            {
                "libraries_root": "/tmp/restored/external/libraries/gtnh",
                "java": "/tmp/restored/external/java/modern/bin/java",
                "notes": "ordinary user notes",
            },
        )

    def test_public_archive_excludes_private_data_even_if_git_lists_it(self):
        names = [
            "src/example.py",
            "local-settings.json",
            "memory/notes.md",
            "models/weights.gguf",
            "runtime/trace.json",
            "external/config.json",
            "PRIVATE-BACKUP.json",
        ]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in names:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("test")
            with (
                patch.object(backup, "ROOT", root),
                patch.object(
                    backup.subprocess,
                    "check_output",
                    return_value=("\0".join(names) + "\0").encode(),
                ),
            ):
                self.assertEqual(backup.public_files(), ["src/example.py"])

    def test_virtual_display_never_falls_back_to_the_desktop(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "display.json"
            p.write_text(json.dumps({"DISPLAY": ":0", "XDG_RUNTIME_DIR": "/run/user/1000"}))
            with patch.object(virtual_display, "INFO", p):
                with self.assertRaises(ValueError):
                    virtual_display.environment()

    def test_legacy_table_is_small_and_does_not_require_a_modded_client(self):
        p = legacy_bindings.prepare()
        self.assertEqual(p["class.net.minecraft.client.Minecraft"], "bao")
        self.assertLess(len(p), 100)
        self.assertIn("signature.net.minecraft.client.Minecraft.tick.0", p)

    def test_virtual_display_identity_is_exact(self):
        flag = str(manage.ROOT / "scripts/virtual_display.py")
        self.assertTrue(manage.matches("display", ["python3", flag, "serve"], manage.ROOT))
        self.assertFalse(
            manage.matches("display", ["python3", flag + "-other", "serve"], manage.ROOT)
        )


if __name__ == "__main__":
    unittest.main()
