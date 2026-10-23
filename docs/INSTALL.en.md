# Installation, operation and troubleshooting

[简体中文](INSTALL.md)

For an existing server, start with `./setup.sh --server-dir /path/to/server`; see SERVER-DEPLOYMENT.en.md and HEADLESS.en.md. This experimental compatibility/evaluation layer should first be used in an isolated test world. Basic operations do not demonstrate complex crafting or arbitrary modpack capability. WSL/WSLg have no end-to-end acceptance.

## System requirements

Local validation used Linux x86_64, KWin 6.8, Xwayland, libei, NVIDIA RTX 5060 8GB and about 30GiB RAM. Windows, macOS, AMD/Intel graphics and other compositor combinations are unverified. A private KWin session can run independently of the current desktop, provided KWin/Xwayland and OpenGL work.

Provide Python 3.11+ (uv recommended), KWin Wayland, Xwayland, dbus-run-session, libX11, libei, OpenGL drivers, C/C++ tools, pkg-config, libei/D-Bus headers, JDK 17+ with javac/jar, git, cmake and zstd. CUDA compilation additionally needs a toolkit; CPU builds do not. The wizard shows missing packages before offering installation and does not replace drivers or system Python/Java.

The 2B language GGUF is about 1.56GB and vision about 0.67GB; VRAM additionally includes caches and rendering. Full GPU placement worked locally. Checkpoints, intermediate F16 files, game assets, Java, traces and snapshots use additional disk; allow at least 40GiB plus space for any complete private snapshot.

## Source and environment

```bash
git clone https://github.com/RhysZhang1/minecraft-compatibility-bench.git
cd minecraft-compatibility-bench
./setup.sh --doctor
./setup.sh
```

SSH cloning is also available at git@github.com:RhysZhang1/minecraft-compatibility-bench.git. Public profiles are templates, so the first clone has no selected instance. Paths are written to ignored local-instances.json. See CONFIGURATION.en.md.

Suggested wizard order:

1. Configure environment/dependencies: create .venv, install the project package and hf; choose conversion dependencies when converting 2B, and prepare ASM for Git-source builds.
2. Build llama.cpp in a new engines/llama.cpp directory, CPU or CUDA. The engine commit is pinned. Existing trees are not reset; an existing compatible binary may be configured instead.
3. Install vanilla client/server/Java, initially 1.20.1, with separate server directory and free game/RCON ports. The wizard records the actual Java for both launch paths.
4. Download/prepare/select 2B. Revisions are pinned; official source weights are SHA256-checked. Language and vision conversions and Q4 quantization are local. Temporary outputs become final files only after successful completion. 9B remains optional and generally needs partial GPU/CPU placement on 8GB VRAM.
5. Run ./setup.sh --verify-models.

For development, install `.[dev]` with pip/uv; the wizard installs the project package with `.[hub]`. pyproject.toml defines packaging, dependencies and the mcbench entry point. Routine inference does not need PyTorch.

Downloads verify official SHA1 per file. Existing corrupt files are reported rather than silently replaced. Java retries validate the full manifest rather than merely checking bin/java. Server installation uses a version-marked temporary directory, publishes only on completion and never overwrites a complete existing world. Reusing a server shows its real path/ports.

### EULA and source archives

Read and accept the [Minecraft EULA](https://aka.ms/MinecraftEULA) yourself. The wizard may copy an already accepted eula.txt; without a valid record startup reports the required path. Scripts do not accept terms for you.

Git and GitHub-generated source archives have no compiled bridge. Startup builds the read-only Java sensors and libei library using JDK/ASM/C dependencies. Custom minecraft-bench-source archives can contain manifest-checked project binaries under release/; another ABI may need rebuilding. Models, worlds and Minecraft runtime files are excluded from public distributions.

## Start and stop

```bash
./start.sh --instance vanilla-1-20-1 --paused --no-open
./stop.sh
```

The instance must first be prepared. start.sh uses the last selected profile and enables model control unless --paused. --no-open suppresses browser launch; the client remains hidden. --profile cpu selects CPU inference while game rendering can remain on GPU. --model 2b/9b selects a checkpoint; stop before changing active placement/model. --timeout controls each readiness stage. `python3 scripts/lifecycle.py status` is read-only.

stop.sh pauses, checkpoints notes, releases input, exits the client, saves/stops managed worlds, then stops model/private display. It also stops registered standalone test servers; connection-only external servers remain running. --force permits a final forced server termination only after graceful/JVM timeouts, risking unsaved progress.

Absolute script paths work from other directories, including paths with spaces. Repeated starts reuse matching services; repeated stops are safe. Stop uses system Python and can work with a damaged .venv. Exact process role/arguments and directories recover lost PID files without killing unrelated Java applications. Stop during startup requests cancellation; failed startup cleans up only newly started components. Port conflicts are reported without killing their owner.

## Dashboard and persistence

Dashboard/model interfaces bind to loopback 8790/8789. Use SSH forwarding for remote viewing. Launcher accounts are not imported; online authentication is outside the current workflow. Managed test copies receive peaceful/keep-inventory rules; external servers keep existing settings. 26.3 uses its newer rule name.

The dashboard shows frames, actual outputs/actions, feedback, command replies and documents. Stable player/offline UUID lets the server retain inventory/position. Notes are isolated by world_id and distinguish facts from suggestions; model process context is rebuilt after restart. Use a new ID/directory for a new world.

## Troubleshooting

| Symptom | Check/action |
|---|---|
| No configured instance / unresolved placeholders | Run setup.sh; resolve local profile paths, do not edit source constants |
| Missing model/template/hashes | Complete model download/conversion or restore a private snapshot |
| Missing ASM/javac | Install JDK, prepare ASM, verify javac is executable |
| libei build failure | Check compiler, pkg-config and libei/D-Bus development files |
| Wrong Java | Install matching runtime; inspect instance and MINECRAFT_JAVA_BIN overrides |
| Port conflict | Use a free port or stop your own conflicting application |
| Interrupted Java/server install | Retry; manifests and staging directories allow recovery |
| Slow world startup | Read logs/server.log and increase timeout; open ports alone are not readiness |
| No frame or isolation | Read display/bridge/client logs; do not point DISPLAY at the desktop |
| Paused after ineffective decisions | Inspect frames/goals/feedback before resuming bounded recovery |
| Low preview FPS | Compare measured render/capture/browser FPS separately from inference latency |
| Duplicate/incomplete process | Stop normally, retain logs; do not use killall java |

Private evidence is under runtime/validation, logs and per-instance episode directories. Sanitize paths, credentials and personal notes before filing an issue.

## Private snapshots and restoration

```bash
./stop.sh
.venv/bin/python scripts/backup.py --full
.venv/bin/python scripts/backup.py --verify backups/backup-manifest-TIMESTAMP.json
```

Source archive, Git bundle and complete private archive are separate. A full archive includes models, managed worlds/player data, notes/traces, Python and declared external Java/resources/engine. Never publish it. Prior snapshots remain intact.

Restore into a new empty directory:

```bash
mkdir minecraft-bench-restored
cd minecraft-bench-restored
tar --zstd -xf /safe/path/PRIVATE-minecraft-bench-full-TIMESTAMP.tar.zst
python3 scripts/restore_private.py --rebind
./setup.sh --doctor
./start.sh --paused --no-open
```

Restoration preserves original configuration copies and rebinds paths. This is not an OS image: compatible drivers, KWin, libei and libraries must exist. Another ABI/distribution may need a rebuilt environment/native library. Temporary-directory restoration on the same host does not establish cross-machine restoration. Clone restore-history.bundle separately to recover Git history; source history and world restoration are distinct operations.
