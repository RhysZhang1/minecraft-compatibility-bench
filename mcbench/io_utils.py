# SPDX-License-Identifier: GPL-3.0-or-later
"""Small JSON transport helpers shared by runtime components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def readjson(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def atomic(path: str | Path, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False))
    tmp.replace(p)
