# Temporary manual intervention

[简体中文](INTERVENTION.md) · [Home](../README.md)

When the model repeats inventory actions, stays in a menu, or gets stuck in terrain, the dashboard can control the same hidden player. No desktop client window or global keyboard/mouse capture is needed.

## Controls

1. Check the latest game image in the dashboard.
2. Select **启用画面点击 / 拖动** (enable frame clicks/dragging). This pauses the model, invalidates pending model actions, and releases held input and sustained mining.
3. In an inventory, menu, crafting table or furnace screen, click directly in the preview. Left-click picks up/places items; right-click uses Minecraft's normal splitting behavior. A drag sends pointer motion while holding the button. Distributing a stack generally requires picking it up with a click first. The Shift checkbox enables Shift-clicks.
4. In the world, use the movement, jump, attack/mining, interaction and camera buttons. A key press lasts 100ms, 300ms, 1 second or 2 seconds. This is bounded input, not continuous remote keyboard capture. Scroll buttons can change the selected hotbar slot.
5. Use **释放全部输入** (release all input) to interrupt held input. Select **交还模型** (return control to the model) when ready. The model starts from a fresh observation. Disabling frame clicks alone does not resume it.

The model stays paused after each manual action, allowing several interventions. Keys and mouse buttons can be held for at most 2 seconds; GUI dragging includes positioning/press/release intervals and takes at most about 2.18 seconds. Gestures outside the image are clamped to its edge; cancelled touch gestures send no action.

## Isolation and cancellation

Input uses the existing private display session's libei channel. It does not inject global input into the user's desktop or capture typing in other applications. Only explicit dashboard controls and an armed preview send input to Minecraft.

Manual and model actions share the control epoch and heartbeat. Taking control, emergency release, client reconnection, screen changes and heartbeat expiry cancel old actions and release input. The model cannot resume, and the instance cannot switch, during an active manual action. Requests from an old session or a changed screen are rejected; inspect the new image before retrying.

Opening inventory or clicking a menu button may itself change screens. The dashboard then reports that the screen/control changed and input was released. This does not necessarily mean the click failed: inspect the resulting image. Clicking the preview in the world does not rotate the camera; use camera buttons instead.

## Records and limits

Manual actions are stored separately in the instance's `interventions/` directory, including `source: human`, input plan, completion/cancellation state, and before/after images. They do not increase model decision counts or enter model action replay fixtures. Continuation notes may retain observed position and inventory after intervention; these facts do not establish model task success.

This feature requires the updated `virtual-x11` private display backend advertising `manual_input`. The older Forge-specific bridge does not support it; unsupported controls are disabled. Modpacks still require matching clients, and custom screens retain their own interaction rules. Human dragging does not change the upstream model's 200ms action protocol or demonstrate model crafting/furnace planning ability.

The service still listens on loopback only. For remote use, follow the SSH forwarding instructions in the README.

## Local acceptance

On 2026-10-23, vanilla 1.20.1 with the real hidden client passed dashboard inventory open/close, clicking to pick up 30 dirt, dragging into three slots of 10, and Shift-clicking back into the original hotbar slot. Resuming during a 2-second hold was rejected; after emergency release, empty held keys and an idle bridge were observed in about 52ms in one local measurement, not a latency guarantee. Returning control resumed real model decisions; pausing again released keys and mining. Manual dragging on other versions and custom modded GUIs has not been individually accepted.
