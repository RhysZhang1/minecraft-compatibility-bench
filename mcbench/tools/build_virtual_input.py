# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Linux private-display input sender using standard libei and D-Bus SDKs."""

import subprocess

from mcbench.paths import ROOT

flags = subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", "dbus-1", "libei-1.0"], text=True
).split()
subprocess.run(
    [
        "cc",
        "-shared",
        "-fPIC",
        "-O2",
        str(ROOT / "input/ei.c"),
        "-o",
        str(ROOT / "input/libgamescaling-ei.build.so"),
        *flags,
    ],
    check=True,
)

(ROOT / "input/libgamescaling-ei.build.so").replace(ROOT / "input/libgamescaling-ei.so")
