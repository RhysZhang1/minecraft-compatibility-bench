# SPDX-License-Identifier: GPL-3.0-or-later
"""Machine-local paths; never embed an author's absolute home in launch code."""

import json
import os
import shutil
from pathlib import Path

from mcbench.paths import ROOT


def settings():
    try:
        return json.loads((ROOT / "local-settings.json").read_text())
    except FileNotFoundError:
        return {}


def value(key, env, default):
    return os.path.expanduser(os.environ.get(env) or settings().get(key) or str(default))


def llama_source():
    return Path(value("llama_source", "LLAMA_CPP_SOURCE", ROOT / "engines/llama.cpp"))


def llama_server():
    return value("llama_server", "LLAMA_SERVER_BIN", llama_source() / "build/bin/llama-server")


def java():
    return value("java", "MINECRAFT_JAVA_BIN", shutil.which("java") or "java")


def save(changes):
    p = ROOT / "local-settings.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({**settings(), **changes}, ensure_ascii=False, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(p)
