# Add a visual-model client to an existing Minecraft server

[简体中文](SERVER-DEPLOYMENT.md)

The wizard performs detection, resource recommendations, explicit connection selection, environment preparation, per-world notes and paused startup. A background visual client is still required; see HEADLESS.en.md.

## Read-only inspection

```bash
./setup.sh --inspect-server /srv/minecraft
./setup.sh --inspect-server /srv/minecraft --version 1.7.10
python3 scripts/deploy_server.py --scan /srv
```

Scanning is bounded to two levels. Inspection reads manifests, version metadata inside JARs, server.properties and known launch arguments, and probes the local game port/process working directory. It never executes unknown scripts or JARs. Reports expose only whether an RCON password exists, not its value.

Checks cover OS/architecture/WSL, cgroup-limited available RAM, free disk, CPU, NVIDIA free VRAM, KWin/tools/libraries, game version/loader, ports, authentication, whitelist, world existence, view distance, difficulty, RCON and -Xmx.

## Recommendations

Automatic preparation supports 2B and 9B. Budget server heap growth, 4GiB for a vanilla client (8GiB modded), and 2GiB for the system before considering model RAM. Existing server heap limits are not reduced to squeeze in a model.

Model RAM estimates are 4GiB for 2B and 10GiB for 9B. GPU estimates require about 6.5GiB/12GiB free VRAM, including vision/context/compute/game headroom. Generous hardware may receive a 9B GPU recommendation; otherwise 2B is preferred, with CPU fallback when VRAM is insufficient. Insufficient RAM blocks automatic deployment.

These are heuristics, not performance or stability guarantees. The wizard checks resources again before saving. AMD/Vulkan and automatic 27B preparation are not implemented.

## Guided deployment

```bash
./setup.sh --server-dir /srv/minecraft
# Or select option 9 in setup.sh
```

After confirmation, prepare project-local Python/tools, llama.cpp when needed, matching client/Java, ASM, model downloads/conversion/hashes, goal, player name, long-term notes and summary interval. Startup builds and validates background input and read-only sensors.

Missing system packages are shown before installation is offered, which may require sudo. Drivers and distribution upgrades are excluded. GPU compilation needs an existing CUDA toolkit; otherwise choose CPU or supply a compatible engine.

### Connect only (default)

The original properties, difficulty, world, whitelist, authentication and launch scripts remain unchanged. The server keeps its existing lifecycle. stop.sh stops only this project's client/model/dashboard, leaves that server alive, disables its management console and applies no test rules.

Online authentication is not integrated and is never disabled automatically. Use an authorized offline test server; its owner must whitelist the chosen player where necessary. Plugin servers may accept matching vanilla clients, but custom behavior needs validation.

### Create a managed copy

Stop the source before copying a world. Select its JAR, extra JVM arguments and new ports. The copy is created under instances/deployed; only that copy receives managed lifecycle and test settings. Source activity is checked again immediately before copying.

Forge/Fabric/NeoForge servers require a matching complete client manifest/JAR/libraries/assets. A vanilla client is not substituted just because the base version matches. Custom launcher behavior may need additional work.

## Retry and persistence

Each instance has its own world_id, player, goal, notes and episode directory. Retrying the same ID/server preserves identity; reusing an ID for another source or management mode is rejected. New worlds should use new IDs.

Profiles and step journals live in ignored local-instances.json and runtime/deployments. Downloads can resume. A configuration success does not imply a connected game; startup acceptance remains necessary.

Documents distinguish observations from unverified suggestions. Model process context does not persist across shutdown. External server worlds are excluded from this project's complete snapshot; back them up through their own stopped-server workflow.
