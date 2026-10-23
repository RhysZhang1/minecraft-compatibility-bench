# Offline fixture provenance and review

[简体中文](README.md)

`golden/replay.json` contains **50 cases and 37 sanitized real input frames**, drawn from local vanilla 26.3 and 1.20.1 runs with GameScaling-2B-S1 Q4_K_M and F16 vision. Replay performs **300 comparisons**: frame hashes, normalized actions, execution gates, observed feedback and recovery decisions. The corpus is a regression contract for the compatibility layer, not a model capability benchmark.

Recorded sequences cover mining/button packets, no-ops, screen changes, item pickup/movement and a stationary menu. Raw outputs are preserved for these selected cases; the sole nonempty reasoning passage was reviewed and contains only generic terrain/tutorial observations. No personal prompt or private note is included.

## Historical image limitation

Old episodes retained the input image, raw output, result state and feedback, but not the exact result image. These fixtures pair **adjacent real input observations**, each with its corresponding recorded game_before state. They do not claim to reproduce historical acknowledgement-to-frame timing or original feedback byte for byte. One final unchanged-frame extension is authored and labeled. An additional 1.20.1 case includes the exact acknowledged result image and its relative post-ack delay. New live episodes save `NNNNNN.after.jpg` for exact post-ack replay in future additions.

## Sanitization

- Allowlist only screen/connection/health/cursor/inventory and relevant position/target fields.
- Replace session identity, translate absolute coordinates by one common integer origin and round positions to four decimals.
- Omit player names, paths, addresses, timestamps, chat, launcher/authentication data, model paths and memory/prompt context.
- Black out the top 64 pixels and bottom 26% of each original frame, then resize to 320×180 and write new PNGs without source metadata. Review the resulting frames for names/chat; masks alone do not guarantee anonymization for every UI.
- Publish hashes of sanitized images, not links to private episode directories. Retain only rounded inference durations.

Authored cases mutate recorded outputs or allowlisted state to exercise epoch cancellation, reconnect, pause, missing acknowledgement, unclosed thoughts, truncated packets and repeated two-screen cycling. They are explicitly labeled **authored**, rather than represented as actual model behavior.

## Expectations and changes

Expected actions/feedback/recovery were frozen during initial fixture preparation, then inspected against explicit invariants: item deltas remain observed changes, cancellation advances no progress counters, reassessment resets history at bounded intervals, and the final stall pauses without generating an input. CI never regenerates `expected`. The mutation test confirms that a changed expectation causes replay failure and the fixture file remains untouched.

```bash
mcbench replay tests/fixtures/golden/replay.json
```

For new cases, copy candidate data into a private review directory first, apply an explicit allowlist, inspect both raw text and images, label measured versus authored cases, and review expected results independently. Include negative cases when changing a model parser. Do not bulk-export runtime/episodes or regenerate expectations automatically to make tests pass.

These screenshots depict Minecraft and retain applicable game-content terms; they do not relicense Minecraft. Original fixture structure and tests use GPL-3.0-or-later. `protocol/chat_template.jinja` is the unmodified Apache-2.0 upstream template from THUSI-Lab/GameScaling-9B-S1 revision `fe9d94cb5f48d645d5099b6856b7a871e803a22d`. It allows protocol checks without downloading weights or accessing a GPU. Upstream license is retained at vendor/GameScaling/LICENSE. The protocol fixture is an explicit exception to the root original-code license.
