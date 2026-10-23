# SPDX-License-Identifier: GPL-3.0-or-later
"""Outlive the monitor while it restarts into another registered instance."""

import argparse
import os
import subprocess

from mcbench import instance_config as instance_config
from mcbench.paths import ROOT

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("instance")
    a = p.parse_args()
    instance_config.config(a.instance)
    subprocess.run(
        [ROOT / "stop.sh"], cwd=ROOT, check=True, env={**os.environ, "MC_SWITCH_CHILD": "1"}
    )
    subprocess.run(
        [ROOT / "start.sh", "--instance", a.instance, "--paused", "--no-open"], cwd=ROOT, check=True
    )
