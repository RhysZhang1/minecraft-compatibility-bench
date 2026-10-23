# WSL support status

[简体中文](WSL.md)

**WSL end-to-end adaptation and testing have not been completed.** Native Linux acceptance does not establish Windows/WSL compatibility.

| Environment | Status |
|---|---|
| Native Linux x86_64 / KWin / NVIDIA | Four-version basic operations and full lifecycle tested locally |
| WSL1 | Unsupported by the current GUI-control backend |
| WSL2 + WSLg | Future target; private compositor, input isolation, rendering and game lifecycle unverified |
| Native Windows | No corresponding background input/capture or lifecycle backend |

WSLg provides X11/Wayland GUI support, and NVIDIA documents CUDA on WSL2. Running model inference or one GUI application does not establish compatibility for this entire stack. Validate CUDA and Minecraft graphics separately.

The critical dependencies are the private KWin session, Xwayland, libei input and actual client rendering. Scripts create their own session rather than sharing Windows/WSLg input. The deployment inspector detects WSL and can find nvidia-smi at /usr/lib/wsl/lib/nvidia-smi, but automatic deployment remains blocked until the full backend is validated. NVIDIA's WSL guidance uses the Windows host driver; do not install a separate Linux display driver inside WSL.

Before declaring WSL2 supported, test on real Windows/WSL2 hardware: environment detection; Java/client/model installation and retries; private display and input with no shared-desktop fallback; movement, inventory, sustained mining/pickup and pause release; simultaneous Windows physical input; independent CPU/GPU inference, graphics and preview metrics; Windows-browser access; repeated/cancelled startup; cleanup, player/world persistence and notes.

No such evidence is available, so no guaranteed WSL installation recipe is offered.

References: [Microsoft WSLg](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps), [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).
