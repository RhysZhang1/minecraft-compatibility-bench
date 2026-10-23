# Vanilla and shared-backend acceptance

[简体中文](VANILLA-VALIDATION.md)

Recorded on 2026-10-23, Asia/Shanghai. These are local execution results, not a reproduction of the paper's benchmark.

| Version | Java | Movement/turn | Inventory | Sustained mining/pickup | Pause release |
|---|---|---|---|---|---|
| 1.7.10 | 8u202 | Passed, about 1.056 blocks | Passed | Dirt destroyed and inventory increased | Passed |
| 1.20.1 | 21 | Passed, about 0.842 blocks | Passed | Same | Passed |
| 1.21.1 | 21 | Passed, about 0.842 blocks | Passed | Same | Passed |
| 26.3 | 25 | Passed, about 0.842 blocks | Passed | Same | Passed |

All used private KWin/Xwayland/libei. glxinfo confirmed NVIDIA rendering. Servers were vanilla with no bridge mod; the vanilla 1.7.10 client did not depend on GTNH. At that milestone 40 automated tests passed, covering protocol, ownership, RCON, memory fact boundaries, world isolation, fresh frames, unknown inventory, UI cycles and archive privacy.

Native input rejects a compositor PID mismatch with -7 before creating EIS input. Tests used private D-Bus only. The legacy modded client also passed cold startup, five callback-isolation checks and inventory toggling with existing items readable.

## Autonomous 2B run in 26.3

88 outputs parsed and received execution confirmation. Median inference was about 1.35s and median cycle about 1.67s; four packets were no-ops. Recorded dirt increased from 1 to 16. This establishes some live actions and item changes, not completion of the wood objective or an apples-to-apples model comparison.

The shared controller removed a fixed extra wait, required acknowledgement followed by a fresh matching frame, coalesced identical idle history and supplied previous-action feedback. Repeated ineffective decisions or two-screen cycling trigger bounded reassessment and then pause, without selecting buttons for the model. Model/checkpoint settings and pack-specific strategy were not changed for this generic controller work.

Private acceptance records remain under runtime/validation. Old unit-test counts describe their original milestone; current package/replay checks are listed in RELEASE-CHECKS.en.md. GPU/game acceptance is separate from offline CI and has not been rerun for every platform or modpack.
