# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay frozen model outputs and observations without a model or game process."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from gamescaling.action import parse_action

from mcbench.decisions import recovery_decision, should_execute
from mcbench.feedback import Feedback, Observation


def action_result(raw: str) -> dict[str, Any]:
    """Expose a stable, JSON-compatible action contract for regression fixtures."""
    action = parse_action(raw)
    return {
        "parsed": action.parsed,
        "truncated": action.truncated,
        "mouse": list(action.mouse),
        "steps": action.steps,
        "history_text": action.history_text,
        "is_noop": action.is_noop,
        "dropped": list(action.dropped),
    }


def replay_file(path: Path) -> dict[str, Any]:
    """Compare replay results to committed expectations; never rewrite them."""
    path = Path(path)
    fixture = json.loads(path.read_text())
    failures: list[dict[str, Any]] = []
    checks = 0

    def compare(label: str, actual: Any, expected: Any) -> None:
        nonlocal checks
        checks += 1
        if actual != expected:
            failures.append({"case": label, "expected": expected, "actual": actual})

    def observe(value: dict[str, Any]) -> Observation:
        image_path = (path.parent / value["frame"]).resolve()
        if not image_path.is_relative_to(path.parent.resolve()):
            raise ValueError("Fixture frame escapes its directory")
        image = image_path.read_bytes()
        compare(value["frame"] + ":sha256", hashlib.sha256(image).hexdigest(), value["sha256"])
        return Observation(image, value.get("metadata", {}), value["game"])

    for sequence in fixture["sequences"]:
        feedback = Feedback(sequence.get("settings", {}))
        for case in sequence["cases"]:
            prefix = sequence["id"] + "/" + case["id"]
            compare(prefix + ":action", action_result(case["raw"]), case["expected"]["action"])
            action = parse_action(case["raw"])
            permitted = should_execute(
                action,
                **case.get(
                    "gate", {"enabled": True, "epoch_matches": True, "session_matches": True}
                ),
            )
            compare(prefix + ":execute", permitted, case["expected"]["execute"])
            if "before" in case:
                result = feedback.record(
                    observe(case["before"]),
                    observe(case["after"]),
                    action,
                    executed=permitted and case.get("acknowledged", True),
                )
                compare(prefix + ":feedback", result, case["expected"]["feedback"])
                compare(
                    prefix + ":recovery",
                    asdict(recovery_decision(feedback)),
                    case["expected"]["recovery"],
                )
    return {"fixture": path.name, "checks": checks, "passed": not failures, "failures": failures}
