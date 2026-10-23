# SPDX-License-Identifier: GPL-3.0-or-later
"""Install official Linux client resources into the workspace, without accounts."""

import argparse
import concurrent.futures
import json
import shutil
import time
from pathlib import Path

from mcbench.paths import ROOT
from mcbench.tools import launch_game
from mcbench.tools.vanilla_servers import MANIFEST, digest, download, fetch_json


def install(version, assets=True):
    entry = next((x for x in fetch_json(MANIFEST)["versions"] if x["id"] == version), None)
    if not entry:
        raise ValueError("官方清单无此客户端版本：" + version)
    meta = fetch_json(entry["url"])
    client = ROOT / "instances" / ("vanilla-" + version + "-client")
    shared = ROOT / "instances/vanilla-runtime"
    client.mkdir(parents=True, exist_ok=True)
    (shared / "versions" / version).mkdir(parents=True, exist_ok=True)
    text = json.dumps(meta, indent=2)
    for p in (client / (version + ".json"), shared / "versions" / version / (version + ".json")):
        p.write_text(text)
    tasks = []

    def queue(item, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        tasks.append((item["url"], target, item["sha1"]))

    queue(meta["downloads"]["client"], client / (version + ".jar"))
    for lib in meta["libraries"]:
        if not launch_game.allowed(lib.get("rules", [])):
            continue
        downloads = lib.get("downloads", {})
        if downloads.get("artifact"):
            queue(downloads["artifact"], shared / "libraries" / downloads["artifact"]["path"])
        classifier = lib.get("natives", {}).get("linux", "").replace("${arch}", "64")
        if classifier and classifier in downloads.get("classifiers", {}):
            item = downloads["classifiers"][classifier]
            queue(item, shared / "libraries" / item["path"])
    index = meta["assetIndex"]
    indexpath = shared / "assets/indexes" / (index["id"] + ".json")
    queue(index, indexpath)

    def work(task):
        url, target, sha = task
        try:
            relative = target.relative_to(shared)
            cached = Path.home() / ".config/hmcl/.minecraft" / relative
            if not target.exists() and cached.is_file() and digest(cached, "sha1") == sha:
                shutil.copy2(cached, target)
        except ValueError:
            pass
        for attempt in range(3):
            try:
                download(url, target, sha)
                return
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, tasks))
    if assets:
        tasks = []
        for item in json.loads(indexpath.read_text())["objects"].values():
            sha = item["hash"]
            queue(
                {
                    "url": "https://resources.download.minecraft.net/" + sha[:2] + "/" + sha,
                    "sha1": sha,
                },
                shared / "assets/objects" / sha[:2] / sha,
            )
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, tasks))
    if not (client / "options.txt").exists():
        (client / "options.txt").write_text(
            "lang:en_us\nmaxFps:60\nrenderDistance:8\nsimulationDistance:8\npauseOnLostFocus:false\nfullscreen:false\nskipMultiplayerWarning:true\n"
        )
    print(
        json.dumps(
            {
                "client": str(client),
                "libraries_root": str(shared),
                "version": version,
                "java": meta.get("javaVersion"),
                "assets_installed": assets,
            },
            indent=2,
        ),
        flush=True,
    )
    return client, shared


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("version")
    p.add_argument("--no-assets", action="store_true")
    a = p.parse_args()
    install(a.version, not a.no_assets)
