# Historical GameScaling × GT New Horizons experiment

[简体中文](GTNH-EXPERIMENT.md)

This records the original GTNH2.8.4 / Minecraft1.7.10 local experiment. Current generic installation and configuration are in INSTALL.en.md and CONFIGURATION.en.md; machine paths belong in private configuration, not source constants.

## Lifecycle and components

start.sh/stop.sh can be called by absolute path from any directory. Startup checks copied client/server, project Python, model hashes and bridge resources, then waits for server console/model health, client connection, isolated input and managed test rules before enabling control. Stop pauses, checkpoints notes, closes client/dashboard, saves/stops the managed world, exits the model and verifies owned processes/ports. Lost PID files are recovered by exact identity. Repeated starts reuse services; cancellation/failure cleans newly started components. Graceful server timeouts preserve the process unless --force explicitly permits final termination.

Options include --profile cpu, `--model 2b` / `--model 9b`, --paused, --no-open and `--timeout 900`. `python3 scripts/lifecycle.py status` inspects processes. Stop uses system Python even if .venv is damaged. Logs are private logs/server.log, client.log, model.log, monitor.log and lifecycle.log; latest acceptance reports live under runtime.

Default model is locally converted official GameScaling-2B-S1 Q4_K_M with matching FP16 vision. The older third-party9B compatibility copy remains selectable. llama.cpp supports CPU/partial/full GPU placement; equivalence to BF16 model capability has not been established. The copied game uses a dedicated offline GameScalingBot. The legacy Forge bridge captures frames and applies local game/GUI events; Java instrumentation blocks physical input and hides the window while preserving rendering. The dashboard at127.0.0.1:8790 shows actual frames/output/actions, RAM/VRAM and notes.

## Reproduction

Obtain the matching client/server and compatible Java through authorized sources, then configure their paths privately. Launcher account files/tokens are not imported. Use setup.sh for environment/resources, scripts/`download_models.sh 2b` and prepare_2b.py for models, extract_gtnh_context.py only for the legacy experiment context, and build_bridge.py for that backend. The engine defaults to workspace engines/llama.cpp and can be overridden by LLAMA_SERVER_BIN. The recorded local engine was commit680a9ae63/build10394.

The official2B revision is8036a8f05659f3ce79c4b98f0ccbee4142a0b53d. Conversion verifies upstream hashes, uses --no-nextn to exclude an MTP declaration without weights, exports language/vision F16 and quantizes language Q4_K_M. Manifest/checksum files record tools and outputs. PyTorch is needed for conversion, not daily inference. 9B preparation uses `download_models.sh 9b` and normalize_gguf.py, followed by stopping and selecting `--model 9b`. First model default is2B; later selection persists.

All language tensors, vision, KV and recurrent state were placed on GPU for2B. Process code/I/O/mappings still use RAM. Disable llama.cpp's old-prompt RAM cache and limit context checkpoints to two to avoid starving the game. Language and vision files are about1.56GB/0.67GB. Three saved screenshot/history replays measured1.274s median2B versus historical17.736s9B/eight-layer placement; peak sampled VRAM3943MiB. Sampling differed and this is a small speed comparison, not a capability evaluation.

The legacy hidden-window backend requires a graphics session/context. The newer generic virtual-x11 backend has separate headless requirements; do not assume the old backend is a session-independent service.

## Console and memory

Managed test copies expose a loopback RCON-backed Minecraft console with actual replies and day/clear/peaceful/keep-inventory/player-list shortcuts. Commands are not operating-system shell commands. Default pause and epoch invalidation discard an inference started before a manual world change. server-settings.json contains managed-test defaults; random RCON credentials stay in private server.properties. Different game versions use different rule names.

The legacy input instrumentation targets lwjgl3ify2.1.16. A signature mismatch terminates the dedicated client instead of falling back to desktop input. verify_input.py checks blocked callbacks, virtual movement/inventory and screenshot changes while pausing model control.

The memory editor saves current goal, fixed instructions and user notes (2000 characters total) for the next cycle and restart. Facts, user text and unverified model suggestions remain separate. Periodic checkpoints record position/health/player/inventory, recent areas and item deltas; external containers are excluded. Stop checkpoints again, while the server owns actual player/world inventory.

A serial summary request runs about every50decisions or on demand (interval10–500). Constrained JSON selects only a suggestion/unknown items; the program writes Markdown. Summaries are never game actions or verified task completion. A2B action model is not assumed to be a reliable general-purpose writer.

Private documents include prompt.md (legacy agent_prompt.md migrates on upgrade), user_notes.md, current.md, state.json, history and summaries. The public default is config/prompt.default.md. Each new episode records injected continuation_memory text/hash; old episodes used agent_memory. History is rebuilt after process restart, and old facts remain time-labeled. New worlds require independent identities/directories.

Preview targets20FPS separately from60FPS game rendering and inference latency. It deduplicates frame timestamps, loads sequentially and decodes before displaying; real FPS and image age are shown. Targets are not guarantees.

## Files, resources and measured limitations

Original source components remain bridge/src, input/src, sensors/src and mcbench; scripts are thin compatibility launchers for mcbench/tools. Model manifests pin source revisions; vendor/GameScaling retains Apache-2.0. Private instances/runtime/notes/models are excluded from Git and public archives.

The legacy managed server uses loopback25565, model8789 and dashboard8790. Inference is local. Original desktop/HMCL files are not overwritten. User-requested resources restored server6G/6G/eight chunks and client2G/8G/eight chunks, with60FPS cap and854×480rendering. Earlier4G/6G/four-chunk/30FPS restrictions were withdrawn. Peaceful and keep-inventory remain managed-test settings.

S1 learned Minecraft trajectories and does not guarantee understanding of this pack's questbook, tech tree or modified recipes. Legacy context extraction was explicit local adaptation, not retraining. Official action tokens/template and six-substep200ms protocol are retained. Stronger models may still face UI/state/protocol limitations; this compatibility layer does not claim to improve upstream reasoning.

Verified behavior includes startup, actual frame/model/action path, isolated hidden input, basic inventory and manual custom-button clicks, bounded mining, server rules and stop/restart persistence. It does not establish autonomous first-quest completion, crafting/tech progression, multi-hour unattended stability, audio perception or broad modern-modpack compatibility.

Complete private snapshots retain worlds/models/notes/runtime and declared external resources; they are never public GitHub assets. Same-host restoration does not establish cross-machine portability. See INSTALL.en.md for safe snapshot and empty-directory restoration commands, and VALIDATION.en.md/ISSUES.en.md for detailed measurements and fixes.
