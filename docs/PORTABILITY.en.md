# Portability and environment

[简体中文](PORTABILITY.md)

## Version boundaries

| Client | Input/capture | Read-only sensors | Local result |
|---|---|---|---|
| Vanilla 1.7.10 / Java 8 | Private KWin/Xwayland/libei | Minimal 69-entry API table | Basic operations passed |
| Vanilla 1.20.1 / Java 21 | Same | Mojang client mappings | Basic operations passed |
| Vanilla 1.21.1 / Java 21 | Same | Mojang client mappings | Basic operations passed |
| Vanilla 26.3 / Java 25, SDL renderer | Same | Readable class names and GUI fallback | Basic operations passed |
| GTNH 2.8.4 / Minecraft 1.7.10 | Original lwjgl3ify process-local input | Original Forge bridge | Legacy startup/input regression passed |
| Other Forge/Fabric packs | Import matching manifests and reuse private session | Base-version mappings; inspect custom UI visually | Not validated pack by pack |

Passing a vanilla version does not validate every modpack. Loader inheritance, JVM/module arguments and custom launch procedures may need adaptation. Pack knowledge and model strategy are excluded from core control logic.

## Configuration

- instance-settings.json: public placeholder templates; a fresh clone has no runnable instance.
- local-instances.json: ignored resolved profiles, server/client locations and world identities.
- local-settings.json: ignored Java/llama.cpp paths; MINECRAFT_JAVA_BIN, LLAMA_SERVER_BIN and LLAMA_CPP_SOURCE override them.
- game-settings.json: shared resource baseline, then per-profile resources. Legacy modded settings retain 6G server/8G maximum client; vanilla profiles allow 4G each.
- control-settings.json: fresh-frame timeout, history length and bounded recovery. No unsupported action-duration setting is advertised.
- model-settings.json: 2B/9B files, GPU placement and integrity manifests.

Keep world_id, player name and UUID when continuing a world. New worlds require separate IDs/directories; world.json rejects accidental note reuse. The wizard imports client/server copies without launcher account files. External servers can be unmanaged; world_loaded can establish readiness without RCON. Their command console is disabled.

## Build from source

Install KWin, Xwayland, libei runtime/development files, D-Bus headers, C tools, pkg-config, JDK, git and zstd. Full local acceptance used Linux x86_64/NVIDIA; other combinations are unverified. Use setup.sh for Python, vanilla client/server/Java and model preparation. Python lives in .venv, Java in instances/java, shared game resources in instances/vanilla-runtime. Repeated downloads verify hashes.

The Java sensor build uses ASM core and tree. Custom source archives may include manifest-checked project binaries in release/; Git checkouts build them locally. Native input libraries may require rebuilding for another ABI.

2B conversion needs llama.cpp, conversion dependencies and pinned official checkpoint files. Download, conversion and selection are explicit steps. CUDA builds need an existing toolkit; CPU builds do not. Build scripts create a new checkout without resetting existing engine trees.

## Isolation and limits

KWin uses --virtual, private D-Bus and separate XDG runtime/config/cache/data. Native input verifies the target bus belongs to the project's compositor. X11 windows are matched to the client PID, not an assumed Minecraft title. No desktop-session fallback exists.

Input stays inside the private session while the game can use NVIDIA rendering. Device isolation and client responses were verified; an adversarial human physical-input test is not claimed. The vanilla Java instrumentation is read-only and requires no server bridge mod. Sensor failures become unknown/inventory_error, never an empty inventory.

The 26.3 game-rule syntax and legacy 1.7.10 command limitations are handled separately. Audio is not provided to the model. Online authentication, custom quest APIs, arbitrary modpack support and long-horizon planning remain outside validated scope.
