# Historical local execution evidence

[简体中文](VALIDATION.md)

This page records earlier tests, not a general claim of model task competence. For current vanilla portability and packaging/replay checks see VANILLA-VALIDATION.en.md and RELEASE-CHECKS.en.md. Raw evidence remains private under runtime and logs.

The early GTNH 2.8.4 / Minecraft 1.7.10 stack used a copied server/client, offline GameScalingBot and llama.cpp. Model files and metadata hashes were checked, including the 9B compatibility copy whose tensor bytes were unchanged. The client completed Forge handshake through the correct startup connection API. Game frames, original generation, normalized actions and actual client completion records were retained.

Private background input was verified through intercepted hardware callback paths, virtual polling/clicks, movement/turning, inventory opening/closing and changing screenshots while the game window was hidden and unfocused. This was device-routing acceptance, not a completed adversarial simultaneous-human-input test.

Manual commands used local RCON with server replies. Peaceful/keepInventory were applied to the managed test copy and save-all persisted the rule. Sending a manual command increments the control epoch, making a pending old inference ineligible for execution. The console UI, player list, keepInventory query, day and clear-weather replies were verified.

Lifecycle checks covered cold readiness, lost PID recovery, repeated start/stop, exact ownership, cancellation and graceful world saving. Source resources and launcher account data were not overwritten. See release checks for later failure-recovery tests.

## 2B switch and measurements

Official 2B checkpoint files were revision/hash checked. Conversion used --no-nextn because the config declares an MTP layer without matching tensors. Local F16 language/vision export and Q4_K_M quantization produced 1,560,461,088-byte language and 668,227,200-byte vision files. --override-tensor '.*=CUDA0' placed all language weights on CUDA, including the otherwise CPU-mapped embedding; 25/25 layers, vision, KV and recurrent buffers used GPU. Program/I/O/file mappings still use RAM.

Three saved screenshot/history replays measured 2B full-GPU median 1.274s against historical 9B/eight-GPU-layer median 17.736s, about 13.93x. Sampled peak VRAM was 3943MiB with at least 3834MiB free. 2B used seed123 while the older baseline did not; these are small local speed measurements, not a controlled capability benchmark. At least 75 confirmed live decisions were recorded with about 1.290s median inference; no first-quest or technology-chain completion was established.

llama.cpp's default old-prompt RAM cache increased RSS to around 12GiB. The final configuration disables it with --cache-ram 0 and limits context checkpoints to two. A 45-second, 17-decision sample showed model RSS at most 1060MiB and available RAM at least 15.99GiB while replay remained about 1.27s. This does not establish a multi-hour memory bound.

## Notes persistence

Goals, instructions and user notes are stored separately from sensor facts and model suggestions. Save/restart tests restored the same offline role, notes and server-managed inventory. A post-resume sample of 25 acknowledged operations in the 1127–1152 range all parsed, with 1.297s median inference; logged context hashes matched injected saved notes. Pending actions invalidated by edits were excluded from completed-operation counts.

Summary requests are constrained JSON and never executed as game actions. Unknown inventory remains unknown. Editing conflicts are detected. Persistent documents do not imply persistence of in-process model context or completion of the goal.

Limits include unverified first quest/crafting/long-horizon progress, no audio input, version-specific legacy lwjgl3ify instrumentation, and no cross-machine restoration or WSL acceptance. Early hidden-window tests depended on a logged-in graphics session; the later private virtual backend has a separately documented session-independent acceptance path.
