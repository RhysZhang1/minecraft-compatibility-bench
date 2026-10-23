# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay saved screenshots/history against the active model; never execute actions."""

import argparse
import base64
import json
import statistics
import subprocess
import threading
import time

from gamescaling.action import ACTION_END, parse_action

from mcbench.paths import ROOT
from mcbench.runtime import Runtime


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", type=int, nargs="+", required=True)
    a = p.parse_args()
    runtime = Runtime(ROOT)
    with runtime.opener.open("http://127.0.0.1:8790/api/status") as r:
        state = json.load(r)
    if state["enabled"] or state["inference_started"]:
        raise SystemExit("Pause and finish the live inference before replaying screenshots")
    runtime.state["goal"] = state["goal"]
    samples = []
    done = threading.Event()

    def sample():
        while not done.is_set():
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                used, free = map(int, result.stdout.strip().split(","))
                samples.append({"time": time.time(), "used_mb": used, "free_mb": free})
            done.wait(0.25)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    results = []
    try:
        for number in a.episodes:
            folder = ROOT / "runtime/episodes"
            runtime.history.clear()
            for old in range(max(1, number - 5), number):
                stem = folder / f"{old:06d}"
                if not stem.with_suffix(".json").exists():
                    continue
                record = json.loads(stem.with_suffix(".json").read_text())
                runtime.history.append(
                    (
                        base64.b64encode(stem.with_suffix(".jpg").read_bytes()).decode(),
                        record["action"],
                    )
                )
            stem = folder / f"{number:06d}"
            previous = json.loads(stem.with_suffix(".json").read_text())
            frame = base64.b64encode(stem.with_suffix(".jpg").read_bytes()).decode()
            prompt = runtime.prompt.make_prompt(frame)
            started = time.monotonic()
            with runtime.request(
                "/completion",
                {
                    "prompt": prompt,
                    "stream": False,
                    "seed": 123,
                    "temperature": 1.0,
                    "top_k": 0,
                    "top_p": 1.0,
                    "min_p": 0.0,
                    "repeat_penalty": 1.0,
                    "n_predict": 768,
                    "stop": [ACTION_END],
                    "cache_prompt": False,
                },
                timeout=600,
            ) as r:
                reply = json.load(r)
            latency = time.monotonic() - started
            raw = "<think>" + reply.get("content", "")
            if (
                ACTION_END not in raw
                and reply.get("stop_type") == "word"
                and reply.get("stopping_word") == ACTION_END
            ):
                raw += ACTION_END
            action = parse_action(raw)
            item = {
                "episode": number,
                "latency": latency,
                "baseline_seconds": previous["latency"],
                "parsed": action.parsed,
                "raw": raw,
                "timings": reply.get("timings", {}),
                "executed": False,
            }
            results.append(item)
            print(
                json.dumps(
                    {k: item[k] for k in ["episode", "latency", "baseline_seconds", "parsed"]},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        done.set()
        thread.join(timeout=6)
    output = {
        "model": state["model"],
        "same_saved_screenshots_and_5_frame_history": True,
        "baseline_note": "Previously recorded 9B/8 GPU layer live timings; current replay uses fixed seed123 and full input processing. This is a small speed comparison, not a task capability evaluation.",
        "results": results,
        "gpu_samples": samples,
        "gpu_peak_mb": max(s["used_mb"] for s in samples),
        "gpu_min_free_mb": min(s["free_mb"] for s in samples),
        "median_seconds": statistics.median(r["latency"] for r in results),
        "baseline_median_seconds": statistics.median(r["baseline_seconds"] for r in results),
    }
    output["median_speedup"] = output["baseline_median_seconds"] / output["median_seconds"]
    target = ROOT / "runtime/2b-replay-benchmark.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(target, flush=True)


if __name__ == "__main__":
    main()
