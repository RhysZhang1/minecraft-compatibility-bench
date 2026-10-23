# SPDX-License-Identifier: GPL-3.0-or-later
"""Instance profiles: pack-independent connection, launch and per-world state."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from mcbench import local_environment as local_environment
from mcbench.paths import ROOT

BACKENDS = {
    "virtual-x11": {
        "minecraft_versions": ["1.7.10", "1.20.1", "1.21.1", "26.3"],
        "client_requirements": ["Linux", "KWin virtual backend", "Xwayland"],
        "server_requirements": "Matching vanilla or modded protocol; server mod not required",
        "input_isolation": True,
    },
    "forge1710-lwjgl3ify": {
        "minecraft_versions": ["1.7.10"],
        "client_requirements": ["Forge 1.7.10", "lwjgl3ify 2.1.x"],
        "server_requirements": "Matching protocol; no server bridge mod required",
        "input_isolation": True,
    },
}


def path(value: str | Path, root: Path | None = None) -> Path:
    p = Path(os.path.expandvars(str(value))).expanduser()
    return p if p.is_absolute() else (root or ROOT) / p


def settings() -> dict[str, Any]:
    data = json.loads((ROOT / "instance-settings.json").read_text())
    private = ROOT / "local-instances.json"
    if private.exists():
        data["instances"].update(json.loads(private.read_text()).get("instances", {}))
    return data


def selected() -> str | None:
    if os.environ.get("MC_INSTANCE"):
        return os.environ["MC_INSTANCE"]
    try:
        return json.loads((ROOT / "runtime/selected-instance.json").read_text())["instance"]
    except (OSError, ValueError, KeyError):
        return settings()["selected"]


def config(key: str | None = None) -> dict[str, Any]:
    key = key or selected()
    all_settings = settings()["instances"]
    if not key:
        raise ValueError(
            "No configured instance. Run ./setup.sh (option 6), or ./setup.sh --server-dir /path/to/server; then ./start.sh --instance ID."
        )
    if key not in all_settings:
        raise ValueError(
            "Unknown instance: "
            + str(key)
            + ". Templates are not runnable instances; configure one with ./setup.sh first."
        )
    return validate(key, all_settings[key])


def validate(key: str, profile: dict[str, Any]) -> dict[str, Any]:
    value = {**profile, "key": key}
    backend = BACKENDS.get(value.get("backend"))
    if not backend or value.get("minecraft_version") not in backend["minecraft_versions"]:
        raise ValueError(
            "该客户端版本需要对应输入后端，不能仅改版本号复用：" + str(value.get("backend"))
        )
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key):
        raise ValueError("实例ID仅限字母数字、短横线和下划线")
    unresolved = re.findall(r"\$\{[^}]+\}", json.dumps(profile))
    if unresolved:
        raise ValueError(
            "Unresolved template values: "
            + ", ".join(sorted(set(unresolved)))
            + ". Fill local-instances.json or run ./setup.sh."
        )
    for field in ("client", "server", "connection"):
        if not isinstance(value.get(field), dict):
            raise ValueError("Instance " + key + " requires an object: " + field)
    c = value["connection"]
    if value["server"].get("managed") and c.get("host") not in ("127.0.0.1", "localhost"):
        raise ValueError("本地托管测试服的客户端地址应为127.0.0.1；连接其他服务器请使用非托管配置")
    if not isinstance(c.get("port"), int) or not 1 <= c["port"] <= 65535:
        raise ValueError("服务器端口无效")
    value.setdefault("world_id", key)
    value.setdefault("player", "GameScalingBot")
    if not re.fullmatch(r"[a-zA-Z0-9_]{1,16}", value["player"]):
        raise ValueError("离线玩家名无效")
    value.setdefault("memory_directory", "memory/sessions/" + key)
    value.setdefault("episodes_directory", "runtime/sessions/" + key + "/episodes")
    value.setdefault("control_file", "runtime/sessions/" + key + "/control.json")
    value.setdefault("initial_goal", "Observe your surroundings and follow the current objective.")
    return value


def select(key: str) -> None:
    config(key)
    p = ROOT / "runtime/selected-instance.json"
    p.parent.mkdir(exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"instance": key}))
    tmp.replace(p)
    os.environ["MC_INSTANCE"] = key


def client_directory(root: Path | None = None) -> Path:
    return path(config()["client"]["directory"], root)


def server_directory(root: Path | None = None) -> Path:
    return path(config()["server"]["directory"], root)


def control_file() -> Path:
    return path(config()["control_file"])


def episodes_directory() -> Path:
    return path(config()["episodes_directory"])


def memory_directory() -> Path:
    return path(config()["memory_directory"])


def managed() -> bool:
    return config()["server"].get("managed", False)


def console_enabled() -> bool:
    return managed() and config()["server"].get("rcon_port") is not None


def java() -> str:
    return (
        str(path(config()["java"]))
        if config().get("java") and not os.environ.get("MINECRAFT_JAVA_BIN")
        else local_environment.java()
    )


def library_root() -> Path:
    return Path(os.environ.get("HMCL_GAME_ROOT", str(path(config()["client"]["libraries_root"]))))


def pack_rules(profile: dict[str, Any] | None = None) -> str:
    c = profile if profile is not None else config()
    text = ""
    if c.get("rules_file"):
        text = path(c["rules_file"]).read_text().strip()
    if c.get("context_file") and path(c["context_file"]).exists():
        context = json.loads(path(c["context_file"]).read_text())
        hints = []
        for quest in context.get("quests", []):
            requirements = []
            for task in quest["tasks"]:
                requirements.extend(
                    str(x["count"]) + " " + (x["ore_dictionary"] or x["item"])
                    for x in task["items"]
                )
            hints.append(quest["title"] + ": " + ", ".join(requirements))
        if hints:
            text += " Existing instance requirements: " + "; ".join(hints) + "."
    return text


def template(key: str, replacements: dict[str, str]) -> dict:
    """Resolve an explicitly selected template without publishing or selecting it."""
    templates = settings().get("templates", {})
    if key not in templates:
        raise ValueError("Unknown instance template: " + key)
    text = json.dumps(templates[key])
    for name, value in replacements.items():
        text = text.replace("${" + name + "}", json.dumps(str(value))[1:-1])
    return validate(key, json.loads(text))
