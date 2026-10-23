# Release checks — 2026-10-23

[简体中文](RELEASE-CHECKS.md)

This record separates historical milestones from current source checks. Model settings and the four recorded vanilla versions are retained.

## v0.1 installation and lifecycle audit

Fixes covered full-manifest Java retries, synchronized standalone-server Java paths, version-marked server staging, EULA validation before directory creation, safe reuse of existing worlds, atomic model conversion outputs, cleanup despite control-file failure, PID recovery by exact identity and continuing shutdown after one standalone-server failure. A real repeated-start failure exposed that KWin's publisher worker has a separate session; supervisor/worker roles are now treated as one service.

49 local tests passed then; clean clones skipped one official-template test before the later fixture migration. A temporary Python environment installed runtime/hub dependencies. Shell/compile checks, clean-source setup/doctor/help, real lost-PID stop, repeated stop/start, foreign-port preservation, interrupted startup and /tmp cold startup were checked. Earlier four-version operation evidence remains in VANILLA-VALIDATION.en.md and was not all repeated by that audit. Git blobs were scanned for private paths, large files and common secret patterns; automated scans do not establish absence of every kind of personal content.

## v0.2 existing-server onboarding

67 tests passed locally then. A temporary vanilla 1.20.1 server exercised read-only inspection, recommendations, environment/client preparation, hash verification, profile registration and notes. Startup and restart cleared DISPLAY/WAYLAND_DISPLAY; the hidden client connected with isolated input and live preview.

The original server.properties remained byte-identical, including hard difficulty. Its process was not owned; stop.sh left it alive/listening. Restart retained world_id and custom notes. Copy-mode activity checks run again immediately before copying. Retry preserves identities. A nonmanaged instance no longer incorrectly requires a server.jar field when starting its client/display.

No minimal fresh distribution, GPU-free machine or WSL hardware was tested. Original project code changed to GPL-3.0-or-later; third-party notices and prior-release grants remain intact. Private evidence includes server-onboarding.json, dashboard capture, attached-stop/restart logs and the wizard log.

## v0.3 packaging, templates and replay

The standard package is mcbench, with a pyproject.toml entry point and no authored sys.path manipulation. Runtime ownership is explicit; loop/prompt/feedback/http are separated. Machine paths were preserved privately before public profiles became placeholder templates with no selected instance. Legacy notes migrate without overwriting user instructions.

The current golden corpus contains 37 sanitized real frames and 50 cases, totaling 300 comparisons for image integrity, action parsing, execution gates, observation feedback and recovery/pause. Authored boundaries are labeled separately from recorded frame pairs. Legacy logs lacked exact post-ack images; adjacent input-frame pairs are documented honestly, and new traces now retain .after.jpg.

CI checks style, tests, replay, source entry points and an installed wheel outside the checkout without GPU/X11 or model/game downloads. It does not claim real GPU/game acceptance. Current detailed counts and local startup/stop evidence are recorded with the release commit; historical counts above are not current totals.

Current validation: **76 unit tests passed with no skips**, both locally on Python 3.11 and from an independently installed Python 3.13 wheel outside the source tree. The final live 1.20.1/2B run parsed eight outputs; seven were acknowledged and saved exact result images. The in-flight packet cancelled by pause was not counted as completed. No loop exception occurred; hidden-window input isolation and pause release passed. This does not claim that the model learned to respawn or completed a goal.

The clean unconfigured workspace reports setup guidance, while doctor works without an instance. Legacy prompt migration preserves original text and respects a newer prompt.md. Snapshot restoration now rebinds editable-install finder constants, including quoted paths, and includes workspace-local engines. These changes do not add WSL/minimal-distribution or repeat all four-version game acceptance claims.
