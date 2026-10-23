# Servers without a desktop environment

[简体中文](HEADLESS.md)

The virtual-x11 backend does not require a physical monitor or a logged-in desktop. Startup creates a KWin virtual output, private D-Bus and Xwayland. It does not depend on an existing DISPLAY/WAYLAND_DISPLAY, a complete Plasma desktop or a display manager.

It still renders a **real Minecraft client**. Server, client and model are separate processes; a minimal Java-server installation needs additional background graphics components.

## Requirements

- Linux x86_64. See WSL.en.md for Windows/WSL limitations.
- KWin 6 exposing RemoteDesktop/libei, Xwayland, D-Bus, libei and libX11.
- Working OpenGL/EGL drivers. CUDA inference working does not prove game rendering works.
- Mesa software OpenGL may be attempted without a discrete GPU, but performance, CPU instructions and game compatibility need validation on the target machine.
- Python and project dependencies; JDK/javac/jar, a C compiler, libei/D-Bus development files, git, cmake and zstd.
- Matching Java, Minecraft client and game assets. A server cannot replace the client.
- CPU/RAM or compatible CUDA for the model. The installer does not replace display drivers.

The wizard shows missing packages and proposed installation commands before offering execution. It does not add unknown repositories, install an entire desktop or upgrade the distribution. Older distributions may lack KWin 6/libei. KWin plugins, Mesa and Qt platform components may be separate packages.

Installed tools do not prove the graphics chain works: acceptance requires a running private session, fresh client frames, readable screen state and isolated input confirmation.

```bash
./setup.sh --inspect-server /srv/minecraft
./setup.sh --server-dir /srv/minecraft
./start.sh --instance YOUR_INSTANCE --paused --no-open
```

Forward port 8790 over SSH and use your own computer's browser. No browser is required on the server; --no-open suppresses browser launch. The dashboard remains on loopback.

## Evidence boundary

Clearing desktop-session variables on the development host is different from installing on a new server with no graphics packages. The former verifies independence from an existing desktop session; the latter requires separate distribution/driver/package acceptance. Missing private-display components are never bypassed by targeting the user's desktop input devices.
