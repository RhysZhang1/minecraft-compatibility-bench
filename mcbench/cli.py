# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed command-line interface; offline replay needs no source workspace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Minecraft compatibility layer and evaluation bench"
    )
    parser.add_argument("--workspace", type=Path, help="Source workspace for live tools")
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay", help="Run frozen regression fixtures offline")
    replay.add_argument("fixtures", nargs="+", type=Path)
    sub.add_parser("doctor", help="Inspect a configured source workspace")
    for action in ("start", "stop", "setup"):
        tool = sub.add_parser(action, help="Run the workspace " + action + " tool", add_help=False)
        tool.add_argument("arguments", nargs=argparse.REMAINDER)
    args, extra = parser.parse_known_args(raw_arguments)
    # argparse can separate unknown flags from their values. Forward the original
    # tail unchanged so lifecycle options keep their order and associations.
    command_index = 0
    while command_index < len(raw_arguments):
        item = raw_arguments[command_index]
        if item == "--workspace":
            command_index += 2
        elif item.startswith("--workspace="):
            command_index += 1
        else:
            break
    forwarded = raw_arguments[command_index + 1 :]
    if args.workspace:
        os.environ["MCBENCH_WORKSPACE"] = str(args.workspace.expanduser().resolve())
    if args.command == "replay":
        if extra:
            parser.error("Unknown replay arguments: " + " ".join(extra))
        from mcbench.replay import replay_file

        results = [replay_file(path) for path in args.fixtures]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return int(any(not result["passed"] for result in results))
    from mcbench.paths import ROOT

    if not (ROOT / "pyproject.toml").is_file() or not (ROOT / "instance-settings.json").is_file():
        parser.error(
            "Live tools require a source checkout. Use mcbench --workspace /path/to/checkout "
            + args.command
        )
    os.chdir(ROOT)
    if args.command in ("doctor", "setup"):
        from mcbench.tools.setup import main as setup

        sys.argv = [
            "mcbench setup",
            *(["--doctor"] if args.command == "doctor" else forwarded),
        ]
        return setup() or 0
    from mcbench.tools.lifecycle import main as lifecycle

    sys.argv = ["mcbench", args.command, *forwarded]
    return lifecycle() or 0


if __name__ == "__main__":
    raise SystemExit(main())
