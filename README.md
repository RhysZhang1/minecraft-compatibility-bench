# Minecraft Compatibility Bench

[简体中文](README.zh-CN.md) · [Install](docs/INSTALL.en.md) · [Existing servers](docs/SERVER-DEPLOYMENT.en.md) · [Headless requirements](docs/HEADLESS.en.md) · [Compatibility](docs/PORTABILITY.en.md) · [WSL status](docs/WSL.en.md)

A pixel-action compatibility layer and evaluation bench for real Minecraft clients. The current model adapter uses GameScaling with llama.cpp. This project provides isolated input, observations, lifecycle management and reproducible behavioral regressions; model capabilities and limitations belong to the upstream checkpoints.

## Can it run on a server without a desktop?

**A monitor and a logged-in desktop session are not required on Linux x86_64, but background graphics components are required.** A hidden Minecraft client renders the model's observations. A Java server alone cannot supply those images.

| Requirement | Purpose |
|---|---|
| KWin 6 with RemoteDesktop/libei support, Xwayland, D-Bus, libei, libX11 | Private display and isolated input |
| Working OpenGL driver, or a compatible Mesa software renderer | Render the hidden client |
| Python 3.11+, JDK, C/C++ tools, pkg-config, development headers | Run and build the compatibility components |
| Matching Minecraft client, assets and Java runtime | Connect to the selected server |
| llama.cpp and model files; compatible CUDA for GPU inference | Run the visual model; CPU inference is also available |

Software rendering and CPU inference can be slow. Local acceptance cleared desktop session variables on a machine with graphics packages already installed; it was **not** a fresh minimal-server installation test. WSL2 and native Windows are not validated. See [headless deployment](docs/HEADLESS.en.md).

## Add a model-controlled client to an existing server

```bash
git clone https://github.com/RhysZhang1/minecraft-compatibility-bench.git
cd minecraft-compatibility-bench

# Read-only inspection and resource recommendation
./setup.sh --inspect-server /path/to/server

# Interactive deployment
./setup.sh --server-dir /path/to/server
```

The wizard inspects hardware, memory limits, free VRAM, game version, loader, ports, authentication, whitelist and heap settings. It reserves resources for the server, client and system before recommending a supported 2B/9B configuration. Recommendations are estimates, not speed or stability guarantees.

After confirmation it prepares a project-local Python environment, llama.cpp, a matching client/Java runtime, model files and per-world notes. Missing system dependencies are shown before installation is offered; the wizard does not replace graphics drivers or upgrade the distribution.

The default connection mode leaves the existing server's files and process under its existing management. A separate managed copy can be prepared after stopping the source server. Modded servers need matching clients. Online account authentication is not implemented, and the wizard does not disable it.

## Start, observe and stop

```bash
./start.sh --instance YOUR_INSTANCE --paused --no-open
./stop.sh
```

Open <http://127.0.0.1:8790/> for live frames, actual model output, actions, feedback and editable continuation notes. Only managed test copies receive default peaceful/keep-inventory settings. External servers retain their settings and do not expose a management console through this tool.

For remote viewing, forward the loopback dashboard:

```bash
ssh -N -L 8790:127.0.0.1:8790 USER@SERVER
```

The saved instance controls model placement. `--profile cpu` explicitly selects CPU inference; stop before changing an active model or placement. Stopping saves notes and shuts down owned components. In connection-only mode, the original server remains running.

A fresh clone has **no selected instance**. `instance-settings.json` contains templates with `${PLACEHOLDERS}` and `_comment` explanations. The wizard writes resolved paths to ignored `local-instances.json`. Unfilled templates fail with setup instructions. See [configuration](docs/CONFIGURATION.en.md).

## Persistence and validated scope

A stable player name/offline UUID allows the server to retain inventory and position. Per-world documents retain goals, observed facts, user notes and explicitly unverified model suggestions. Model process context itself does not survive shutdown.

Local basic-operation acceptance covers vanilla **1.7.10, 1.20.1, 1.21.1 and 26.3**: movement, inventory, sustained mining/pickup and pause release. This does not establish complex crafting, arbitrary mod support or long-horizon task ability. See [recorded validation](docs/VANILLA-VALIDATION.en.md) and [release checks](docs/RELEASE-CHECKS.en.md).

## Develop and replay offline

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mcbench replay tests/fixtures/golden/replay.json
.venv/bin/ruff check mcbench scripts tests
.venv/bin/ruff format --check mcbench scripts tests
```

The standard Python package is `mcbench/`: `loop` coordinates decisions, `prompt` formats checkpoint inputs, `feedback` compares observations, and `http` serves the local dashboard. An explicitly constructed `Runtime` owns mutable state; importing runtime modules starts no processes or reads an instance. Workspace scripts are compatibility launchers, with implementations in `mcbench/tools/`.

Golden fixtures contain sanitized real input frames and raw outputs, plus clearly labeled authored safety cases. Replay checks actions, feedback and recovery without GPU, X11, model downloads or inference. It detects changes in adapter behavior, not changes in model intelligence. Wheels can run replay outside the source checkout; live tools also require a source workspace containing Java/native sources and configuration.

[Contributor guide](docs/CONTRIBUTING.en.md) · [Fixture provenance](tests/fixtures/README.en.md).

## License and upstream

Original compatibility code, tools and dashboard use **GPL-3.0-or-later**; see [LICENSE](LICENSE) and [licensing scope](LICENSING.md). Third-party material retains its original terms, including vendored GameScaling (Apache-2.0), ASM (BSD-3-Clause), libei (MIT), and the checkpoint template fixture (Apache-2.0). Model weights and Minecraft runtime files are not distributed.

[GameScaling](https://gamescaling.github.io/) · [Models](https://huggingface.co/THUSI-Lab/GameScaling) · [Paper](https://arxiv.org/abs/2610.28698) · [llama.cpp](https://github.com/ggml-org/llama.cpp).
