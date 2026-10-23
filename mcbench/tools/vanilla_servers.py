# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent loopback vanilla server testbeds; no client support is implied."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

from mcbench import local_environment as local_environment
from mcbench import server_console as server_console
from mcbench.paths import ROOT

REGISTRY = ROOT / "local-vanilla-servers.json"
MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"


def registry():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def fetch_json(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.load(response)
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def download(url, target, sha1):
    target = Path(target)
    if target.exists():
        if digest(target, "sha1") != sha1:
            raise ValueError("已有文件校验失败，不覆盖：" + str(target))
        return
    tmp = target.with_suffix(".partial")
    print("下载官方文件：" + url, flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as f:
        shutil.copyfileobj(response, f)
    if digest(tmp, "sha1") != sha1:
        raise ValueError("官方文件SHA1校验失败，未使用下载结果")
    tmp.replace(target)


def version_of(jar):
    with zipfile.ZipFile(jar) as z:
        if "version.json" in z.namelist():
            return json.loads(z.read("version.json"))
    return {}


def require_eula(path):
    path = Path(path).expanduser()
    if not path.is_file() or not re.search(r"^\s*eula\s*=\s*true\s*$", path.read_text(), re.M):
        raise ValueError(
            "服务器缺少既有EULA接受记录："
            + str(path)
            + "。请自行阅读 https://aka.ms/MinecraftEULA 后配置；脚本不会代为接受。"
        )
    return path


def write_wrappers(folder, key):
    import shlex

    for action in ("start", "stop"):
        script = Path(folder) / (action + ".sh")
        script.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nexec python3 "
            + shlex.quote(str(ROOT / "scripts/vanilla_servers.py"))
            + " "
            + action
            + " "
            + shlex.quote(key)
            + "\n"
        )
        script.chmod(0o755)


def create(version, base, port=25567, rcon=25587, source=None, eula_source=None, java=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", version) or version in (".", ".."):
        raise ValueError("版本号无效")
    if not (1 <= port <= 65535 and 1 <= rcon <= 65535) or port == rcon:
        raise ValueError("端口无效")
    base = Path(base).expanduser().resolve()
    folder = base / ("vanilla-" + version)
    if folder.exists():
        raise ValueError("目录已存在，不覆盖：" + str(folder))
    if eula_source:
        eula_source = require_eula(eula_source)
    metadata = None
    if source:
        source = Path(source).expanduser().resolve()
        found = version_of(source)
        if found.get("id") and found["id"] != version:
            raise ValueError("源JAR实际版本与请求不一致")
    else:
        cached = ROOT / "instances" / ("vanilla-" + version + "-client") / (version + ".json")
        if cached.exists():
            metadata = json.loads(cached.read_text())
        else:
            entry = next((x for x in fetch_json(MANIFEST)["versions"] if x["id"] == version), None)
            if not entry:
                raise ValueError("官方版本清单中没有该版本")
            metadata = fetch_json(entry["url"])
        if "server" not in metadata["downloads"]:
            raise ValueError("此版本无官方服务器下载")
    # All validation before creating the destination; an existing server is never touched.
    destination = folder
    folder = base / (".vanilla-" + version + ".installing")
    marker = folder / "install-state.json"
    if folder.exists() and (
        not marker.is_file() or json.loads(marker.read_text()).get("version") != version
    ):
        raise ValueError("安装临时目录不属于此版本，保留原文件：" + str(folder))
    folder.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": version}))
    if source:
        shutil.copy2(source, folder / "server.jar")
    else:
        item = metadata["downloads"]["server"]
        download(item["url"], folder / "server.jar", item["sha1"])
        (folder / "official-version.json").write_text(json.dumps(metadata, indent=2))
    if eula_source:
        shutil.copy2(eula_source, folder / "eula.txt")
    password = secrets.token_hex(32)
    values = {
        "server-ip": "127.0.0.1",
        "server-port": str(port),
        "enable-rcon": "true",
        "rcon.port": str(rcon),
        "rcon.password": password,
        "online-mode": "false",
        "level-name": "test-world",
        "difficulty": "peaceful" if version != "1.7.10" else "0",
        "view-distance": "8",
        "simulation-distance": "8",
        "max-players": "4",
        "spawn-protection": "0",
        "motd": "Isolated compatibility test " + version,
    }
    p = folder / "server.properties"
    p.write_text("\n".join(k + "=" + v for k, v in values.items()) + "\n")
    p.chmod(0o600)
    folder.rename(destination)
    folder = destination
    major = {"1.7.10": 8, "1.20.1": 17, "1.21.1": 21, "26.3": 25}.get(version)
    runtime = ROOT / "instances/java" / str(major) / "bin/java"
    if not java:
        from mcbench import instance_config as instance_config

        configured = (
            instance_config.settings()["instances"]
            .get("vanilla-" + version.replace(".", "-"), {})
            .get("java")
        )
        java = (
            str(runtime)
            if runtime.exists()
            else str(instance_config.path(configured))
            if configured
            else local_environment.java()
        )
    item = {
        "version": version,
        "directory": str(folder),
        "port": port,
        "rcon_port": rcon,
        "java": java,
        "server_sha256": digest(folder / "server.jar"),
        "memory": {"min": "1G", "max": "4G"},
        "created_at": time.time(),
    }
    values = registry()
    key = version
    if key in values:
        key = version + "-" + str(int(time.time()))
    values[key] = item
    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, indent=2))
    tmp.chmod(0o600)
    tmp.replace(REGISTRY)
    # Small local wrappers refer back to the project manager; backup restore notes describe rebinding.
    write_wrappers(folder, key)
    (folder / "README.txt").write_text(
        "独立原版服务器 "
        + version
        + "\n此服务器能启动不代表AI客户端已支持本版本。\n仅监听本机；离线测试。已有EULA接受记录仅在显式指定源文件时复制。\n"
    )
    print(json.dumps({"key": key, **item}, ensure_ascii=False, indent=2))
    return key


def owned(item):
    from mcbench.tools import manage

    folder = Path(item["directory"]).resolve()
    p = folder / "server.pid"
    try:
        candidates = [int(p.read_text())]
    except (OSError, ValueError):
        candidates = []
    candidates.extend(
        int(p.name)
        for p in Path("/proc").iterdir()
        if p.name.isdigit() and int(p.name) not in candidates
    )
    for pid in candidates:
        info = manage.inspect(pid)
        if not info:
            continue
        args, cwd = info
        if (
            cwd == folder
            and Path(args[0]).name == "java"
            and "-jar" in args
            and args.index("-jar") + 1 < len(args)
            and args[args.index("-jar") + 1] == "server.jar"
        ):
            return pid
    return None


def command(item, text):
    return server_console.execute(text, Path(item["directory"]) / "server.properties")


def start(key):
    item = registry()[key]
    folder = Path(item["directory"])
    if owned(item):
        print("已运行：" + key)
        return
    require_eula(folder / "eula.txt")
    for port in (item["port"], item["rcon_port"]):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    fifo = folder / "console.fifo"
    if not fifo.exists():
        os.mkfifo(fifo, 0o600)
    fd = os.open(fifo, os.O_RDWR)
    try:
        with (folder / "console.log").open("ab") as log:
            p = subprocess.Popen(
                [
                    item["java"],
                    "-Xms" + item["memory"]["min"],
                    "-Xmx" + item["memory"]["max"],
                    "-jar",
                    "server.jar",
                    "nogui",
                ],
                cwd=folder,
                stdin=fd,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    finally:
        os.close(fd)
    (folder / "server.pid").write_text(str(p.pid))
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if not owned(item):
            raise RuntimeError("服务器提前退出；检查 " + str(folder / "console.log"))
        try:
            output = command(item, "list")
            settings = []
            rule = (
                "minecraft:keep_inventory" if item["version"].startswith("26.") else "keepInventory"
            )
            for text in (
                "difficulty peaceful",
                "gamerule " + rule + " true",
                "gamerule " + rule,
                "save-all",
            ):
                reply = command(item, text)
                if any(
                    x in reply
                    for x in [
                        "Incorrect argument",
                        "Unknown or incomplete command",
                        "Unknown game rule",
                    ]
                ):
                    raise ValueError("设置验证失败：" + text + " / " + reply)
                settings.append({"command": text, "output": reply})
            result = {
                "time": time.time(),
                "version": item["version"],
                "pid": p.pid,
                "list": output,
                "settings": settings,
                "client_tested": False,
            }
            (folder / "validation.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return result
        except (OSError, ConnectionError):
            time.sleep(0.5)
    raise TimeoutError("服务器命令接口等待超时")


def stop(key, force=False):
    item = registry()[key]
    pid = owned(item)
    if not pid:
        return
    folder = Path(item["directory"])

    def terminate(sig):
        current = owned(item)
        if current != pid:
            return
        try:
            if os.getpgid(pid) == pid:
                os.killpg(pid, sig)
            else:
                os.kill(pid, sig)
        except ProcessLookupError:
            pass

    try:
        fd = os.open(folder / "console.fifo", os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, b"save-all\nstop\n")
        finally:
            os.close(fd)
    except OSError:
        terminate(signal.SIGTERM)
    deadline = time.monotonic() + 90
    while owned(item) and time.monotonic() < deadline:
        time.sleep(0.2)
    if owned(item):
        terminate(signal.SIGTERM)
        deadline = time.monotonic() + 30
        while owned(item) and time.monotonic() < deadline:
            time.sleep(0.2)
    if owned(item) and force:
        terminate(signal.SIGKILL)
        deadline = time.monotonic() + 5
        while owned(item) and time.monotonic() < deadline:
            time.sleep(0.2)
    if owned(item):
        raise RuntimeError("仍在保存，保留进程：" + key)
    (folder / "server.pid").unlink(missing_ok=True)
    print("已保存并停止：" + key)


def stop_all(force=False):
    errors = []
    for key in registry():
        try:
            stop(key, force)
        except Exception as exc:
            errors.append(key + ": " + str(exc))
    if errors:
        raise RuntimeError("\n".join(errors))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["create", "list", "start", "stop", "stop-all"])
    p.add_argument("version", nargs="?")
    p.add_argument("--base", default=str(Path.home() / "Desktop/MC26.3/tests"))
    p.add_argument("--port", type=int, default=25567)
    p.add_argument("--rcon-port", type=int, default=25587)
    p.add_argument("--source")
    p.add_argument("--eula-source")
    a = p.parse_args()
    if a.action == "list":
        for k, v in registry().items():
            print(k, v["directory"], "running=" + str(owned(v)))
    elif a.action == "create":
        version = a.version or input("Minecraft版本（例如1.7.10、26.3）: ").strip()
        create(version, a.base, a.port, a.rcon_port, a.source, a.eula_source)
    elif a.action == "start":
        start(a.version)
    elif a.action == "stop":
        stop(a.version)
    else:
        stop_all()


if __name__ == "__main__":
    main()
