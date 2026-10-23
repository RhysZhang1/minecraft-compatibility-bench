# SPDX-License-Identifier: GPL-3.0-or-later
import os
import subprocess
import sys

from mcbench import instance_config as instance_config
from mcbench.paths import ROOT

subprocess.run([sys.executable, str(ROOT / "scripts/build_input.py")], check=True)
LIB = instance_config.library_root() / "libraries"
forge = list(LIB.glob("net/minecraftforge/forge/1.7.10*/*universal.jar"))
if not forge:
    raise RuntimeError("缺少Forge 1.7.10编译依赖；请运行setup.sh检查环境")
build = ROOT / "bridge/build"
build.mkdir(parents=True, exist_ok=True)
cp = os.pathsep.join(
    map(
        str,
        [
            ROOT / "input/gamescaling-input-state.jar",
            forge[0],
            *LIB.glob("com/google/code/gson/gson/*/*.jar"),
            *LIB.glob("com/google/guava/guava/17.0/*.jar"),
        ],
    )
)
subprocess.run(
    [
        "javac",
        "--release",
        "8",
        "-cp",
        cp,
        "-d",
        str(build),
        str(ROOT / "bridge/src/GameScalingBridge.java"),
    ],
    check=True,
)
target = instance_config.client_directory() / "mods/GameScalingBridge-1.0.jar"
target.parent.mkdir(exist_ok=True)
subprocess.run(["jar", "cf", str(target), "-C", str(build), "."], check=True)
print(target)
