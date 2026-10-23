# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure execution and recovery gates shared by live control and offline replay."""

from dataclasses import dataclass

from gamescaling.action import Action

from mcbench.feedback import Feedback


@dataclass(frozen=True)
class RecoveryDecision:
    reset_history: bool
    pause: bool
    reason: str


def should_execute(
    action: Action, *, enabled: bool, epoch_matches: bool, session_matches: bool
) -> bool:
    """A parsed packet alone is insufficient authorization to execute it."""
    return bool(action.parsed and enabled and epoch_matches and session_matches)


def recovery_decision(feedback: Feedback) -> RecoveryDecision:
    """Recover by observing again, then pause; never invent a game input."""
    pause = feedback.phase == "stalled"
    reason = "stalled" if pause else "reassess" if feedback.reset_history else "none"
    return RecoveryDecision(feedback.reset_history, pause, reason)
