# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional small ASM build SDK from the official Maven Central repository."""

import hashlib
import json
import urllib.request

from mcbench.paths import ROOT
from mcbench.tools.vanilla_servers import download


def prepare():
    folder = ROOT / "sensors/sdk"
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ("asm", "asm-tree"):
        url = (
            "https://repo.maven.apache.org/maven2/org/ow2/asm/" + name + "/9.8/" + name + "-9.8.jar"
        )
        with urllib.request.urlopen(url + ".sha1", timeout=60) as response:
            sha = response.read().decode().strip()
        target = folder / (name + "-9.8.jar")
        download(url, target, sha)
        records.append(
            {"url": url, "sha1": sha, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    (folder / "provenance.json").write_text(json.dumps(records, indent=2))
    print("ASM SDK ready", flush=True)


if __name__ == "__main__":
    prepare()
