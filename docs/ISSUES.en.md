# Adaptation issue log

[简体中文](ISSUES.md)

## Preview and game resources

The old bridge captured 1FPS and the page refreshed every 1.5s, so the web preview was below 1FPS even when the game/server were healthy. Client cap is now 60FPS and capture/browser target 20FPS. Frame fetching is independent of status polling/inference, deduplicates timestamps, decodes before swapping, avoids queued requests and releases old Blob URLs. Actual render/capture/browser FPS and image age are displayed separately.

A 26-sample run measured game 48.7–61.1FPS, capture median 16.9FPS, browser about 17.1FPS, image age 21–33ms, server 20TPS/1.855ms mean tick, available RAM at least 10.15GiB and total VRAM at most 4263MiB. The 20FPS value is a target. Mining regression still obtained one dirt item. Recorded sustained-input packets alone do not establish useful block selection.

An old client's fresh-looking snapshot could make its replacement appear ready too soon; startup now removes the old generated state before launching a replacement. A regression test covers this.

## Sustained mining

A 200ms action packet previously released every key before the next inference, resetting mining progress. Only in-game LB held across all six substeps may now continue on the same target, with no conflicting button. Target/slot/screen/session/epoch changes, stale heartbeat and a ten-second cap release it. All other keys release normally. A 250ms safety heartbeat has a 1500ms validity window. Manual commands wait for release; cancelled completion is not counted as execution.

Three isolated 200ms attacks separated by 1.4s did not break dirt; one sustained hold broke it in about 0.85s and picked up one item. Pause, heartbeat expiry, target change and timeout released the actual virtual button. This was controlled acceptance, not autonomous goal completion.

Early resource reductions were reversed: legacy server returned to 6G/6G and eight chunks, client to 2G/8G and eight chunks. A 46-sample 120FPS-era run measured 106.3–120.2FPS, server 20TPS, 1.853–1.916ms mean tick, available RAM at least 9.48GiB and total VRAM at most 4022MiB. Low preview rate and configured view distance did not establish server TPS shortage. The later client cap is 60FPS.

## Continuation notes

Server saves do not preserve the model's goal/history. Per-world documents and editable UI now retain goal/instructions/user notes with context hashes in each episode. Facts come from sensors; JSON-constrained summaries only select suggestions/unknowns. Task completion is unverified. Failed inventory reads differ from empty inventory; moving slots does not imply item acquisition/loss, and external containers are outside the snapshot. Atomic writes, archives and revision checks protect edits; private notes stay out of public source.

## Legacy client and checkpoint issues

- Inherited duplicate libraries selected Guava15 and broke Forge access transforms; use the launcher's last-library override semantics, selecting Guava17.
- jinput-platform provides native files without a normal JAR; extract its Linux natives separately.
- Use an independent copied client/server and loopback ports, excluding launcher credentials.
- Custom Main Menu replaces the usual main menu; connection logic handles its class and reconnects.
- Direct GuiConnecting construction bypassed Forge handshake setup and caused playClientBlock failure; use FMLClientHandler.connectToServerAtStartup.
- GUI interaction needs real screen click/release/drag/key events, not only game KeyBinding state.
- The third-party 9B GGUF contains blocks0–31 but declares33/MTP1 with no matching extra tensors. A separate compatibility copy changes metadata to32/MTP0, retains original files and verifies all tensor bytes unchanged. The unused recurrent-layer array remains historical metadata; interval4 derives the verified first32 pattern.
- Query the actual per-process /props media_marker; a hardcoded marker causes image-count mismatch.
- Restore a stripped action-end tag only when stop_type/stopping_word confirms the real boundary. Unclosed thought text cannot authorize an action.
- lwjgl3ify cursor mutation could see a null GLFW handle. Use logical local cursor state and queued local mouse events; BetterQuesting Quests/Bookmarks navigation was manually verified.
- Execute the first 33ms substep immediately on packet acceptance so a short click cannot expire before the next render event.
- Resume decision numbering after monitor restart and record actual acknowledgement/results.
- Early item misidentification and legacy task hints were context adaptation, not training or proof of reliable pack knowledge.

## Hidden input, console and lifecycle

Process-local Java instrumentation blocks physical GLFW callbacks/polling for the legacy client while permitting scoped virtual GUI input. Bootstrap-shared state avoids duplicate classloader state. Hidden windows retain rendering with virtual focus and no desktop cursor capture. Five callback types, virtual movement/turn/inventory and fresh screenshots passed.

The RCON implementation handles 1.7.10's separate authentication/command/reply-boundary flow, fragmented UTF-8, bounded output and failure cases. Credentials stay in private properties. HTTP validates local host/origin and JSON; commands are Minecraft commands rather than shell input. Manual changes pause by default and invalidate old inference.

Lifecycle uses exact command/working-directory signatures rather than generic path substring matching. It recovers lost PID files, locks startup, cancels pending startup/switch work, reclaims only owned components and saves managed worlds before final termination. Model hash checks cache file identity/size/times against expected hashes. Failed installation/conversion never publishes incomplete final artifacts.

## Shared vanilla backend

26.3 SDL windows lack the old WM_NAME; locate by client PID and UTF-8 title. GUI state moved to gui.screen(), requiring a read-only API fallback. Its test server uses the new minecraft:keep_inventory rule. XTEST delivery failed locally, so the private KWin/libei path uses the correct pointer/button devices. Initialize capture with a bounded small event, then apply the model's full relative displacement.

Obfuscated methods can share name/arity but differ in return type; sensor mapping now checks both. Failed reads are unknown. Vanilla1.7.10 lacks modern fill/view-angle teleport options; tests use supported block commands and actual mouse turns. When Forge/MCP remote downloads failed, a minimal69-entry API alias table avoided requiring a modded vanilla client.

Fixed waits were removed in favor of acknowledgement-gated fresh frames. Feedback detects stationary decisions and repeated two-screen cycles, performs bounded reassessment and pauses without choosing UI buttons. No task-completion claim is inferred from image changes. Standalone server retries, conversion publication, EULA prechecks and compositor publisher ownership are covered in release checks.

## Connection-only onboarding and current refactor

Nonmanaged profiles originally failed because manage.start constructed server.jar arguments even for client/display startup. Server arguments are now built only for a server role. External servers keep their own properties, processes and disabled dashboard console. Current pyproject packaging, explicit Runtime, template-only public profiles and sanitized golden replay are documented in CONTRIBUTING.en.md and fixture provenance.

Modern modpacks, online authentication, audio and cross-machine/WSL acceptance remain open boundaries.
