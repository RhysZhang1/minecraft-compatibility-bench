# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only host/server inspection and conservative deployment planning. stdlib only."""

import csv
import ctypes.util
import io
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import zipfile
from pathlib import Path

GIB = 1024**3
SUPPORTED = ("1.7.10", "1.20.1", "1.21.1", "26.3")
JAVA = {"1.7.10": 8, "1.20.1": 17, "1.21.1": 21, "26.3": 25}


def properties(path):
    result = {}
    if Path(path).is_file():
        for line in Path(path).read_text(errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "!")) and "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
    return result


def safe_json(path, limit=2 * 1024 * 1024):
    try:
        p = Path(path)
        if p.stat().st_size > limit:
            return {}
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def version_in_jar(path):
    """Read metadata only; never executes a server JAR or start script."""
    result = {}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "version.json" in names:
                info = z.getinfo("version.json")
                if info.file_size < 1024 * 1024:
                    data = json.loads(z.read(info))
                    result.update(version=data.get("id"), java=data.get("java_version"))
            if (
                not result.get("version")
                and "META-INF/versions.list" in names
                and z.getinfo("META-INF/versions.list").file_size < 1024 * 1024
            ):
                for line in z.read("META-INF/versions.list").decode().splitlines():
                    fields = line.split()
                    if len(fields) >= 2 and re.fullmatch(
                        r"(?:1\.\d+(?:\.\d+)?|26\.\d+)", fields[1]
                    ):
                        result["version"] = fields[1]
                        break
            if any(n.startswith(("net/minecraftforge/", "net/neoforged/")) for n in names):
                result["loader"] = "forge"
            elif any(n.startswith("net/fabricmc/") for n in names):
                result["loader"] = "fabric"
            elif any(n.startswith(("io/papermc/", "org/bukkit/")) for n in names):
                result["loader"] = "plugins"
    except (OSError, ValueError, zipfile.BadZipFile, KeyError):
        pass
    return result


def heap_gib(text):
    values = []
    for value, unit in re.findall(r"-Xmx([0-9]+)([kKmMgG]?)", text):
        values.append(
            int(value) * {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[unit.lower()] / GIB
        )
    return max(values, default=0)


def running_server(folder):
    result = []
    for p in Path("/proc").glob("[0-9]*"):
        try:
            if (p / "cwd").resolve() != folder:
                continue
            argv = (p / "cmdline").read_bytes().decode().split("\0")
            if Path(argv[0]).name != "java":
                continue
            status = (p / "status").read_text()
            rss = re.search(r"^VmRSS:\s+(\d+)", status, re.M)
            result.append(
                {
                    "pid": int(p.name),
                    "rss_gib": int(rss[1]) * 1024 / GIB if rss else 0,
                    "heap_gib": heap_gib(" ".join(argv)),
                }
            )
        except (OSError, ValueError, UnicodeError):
            pass
    return result


def inspect_server(directory, version=None):
    folder = Path(directory).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("服务器目录不存在：" + str(folder))
    props = properties(folder / "server.properties")
    candidates = []
    versions = set()
    loader = "vanilla"
    # Top-level jars, official bundled metadata, and known loader metadata only.
    jars = sorted(folder.glob("*.jar"))
    for jar in jars:
        data = version_in_jar(jar)
        if data.get("version"):
            versions.add(data["version"])
        if data.get("loader"):
            loader = data["loader"]
        candidates.append({"name": jar.name, **data})
    for name in ("official-version.json", "version.json"):
        data = safe_json(folder / name)
        if data.get("id"):
            versions.add(data["id"])
    if not versions:
        log = folder / "logs/latest.log"
        if log.is_file():
            with log.open(errors="replace") as f:
                text = f.read(128 * 1024)
            found = re.findall(r"Starting minecraft server version ([0-9.]+)", text, re.I)
            if found:
                versions.add(found[-1])
    install = safe_json(folder / "install_profile.json")
    if isinstance(install.get("minecraft"), str):
        versions.add(install["minecraft"])
    if (folder / "libraries/net/minecraftforge").exists() or any(
        "forge" in j.name.lower() for j in jars
    ):
        loader = "forge"
    if (folder / "libraries/net/neoforged").exists():
        loader = "neoforge"
    if any("fabric" in j.name.lower() for j in jars) or (folder / ".fabric").exists():
        loader = "fabric"
    if any("paper" in j.name.lower() or "spigot" in j.name.lower() for j in jars):
        loader = "plugins"
    scripts = []
    for pattern in ("*.sh", "*.bat", "*jvm*args*.txt", "*java*args*.txt"):
        for p in folder.glob(pattern):
            if p.is_file() and p.stat().st_size < 256 * 1024:
                scripts.append(p.read_text(errors="replace"))
    configured_heap = max((heap_gib(s) for s in scripts), default=0)
    active = running_server(folder)
    configured_heap = max([configured_heap] + [v["heap_gib"] for v in active])
    detected = next(iter(versions)) if len(versions) == 1 else None
    if version and versions and version not in versions:
        raise ValueError("指定版本与服务器元数据不一致：" + ", ".join(sorted(versions)))
    detected = version or detected
    try:
        port = int(props.get("server-port", "25565"))
    except ValueError:
        raise ValueError("server-port不是有效端口")
    if not 1 <= port <= 65535:
        raise ValueError("server-port超出范围")
    host = props.get("server-ip", "").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    # Probe only loopback; do not send credentials or scan remote networks.
    listening = False
    if host in ("127.0.0.1", "localhost", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.25):
                listening = True
        except OSError:
            pass
    world = props.get("level-name", "world")
    try:
        world_exists = (folder / world).resolve().is_relative_to(folder) and (
            folder / world
        ).is_dir()
    except OSError:
        world_exists = False
    warnings = []
    if not detected:
        warnings.append("版本无法唯一识别，请核实后指定--version；不会根据文件名猜测")
    if loader in ("forge", "neoforge", "fabric"):
        warnings.append("需要同版本、同加载器及匹配模组的客户端，不能自动替换成原版客户端")
    online = props.get("online-mode", "true").lower() != "false"
    if online:
        warnings.append("当前为在线认证；本工具尚未接入正版登录，不会自动关闭认证")
    if props.get("white-list", "false").lower() == "true":
        warnings.append("已开启白名单，需由服主允许所选AI角色加入")
    return {
        "directory": str(folder),
        "version": detected,
        "version_candidates": sorted(versions),
        "supported_version": detected in SUPPORTED,
        "loader": loader,
        "jar_candidates": candidates,
        "connection": {"host": host, "port": port},
        "online_mode": online,
        "white_list": props.get("white-list", "false").lower() == "true",
        "eula_accepted": properties(folder / "eula.txt").get("eula", "").lower() == "true",
        "world_name": world,
        "world_exists": world_exists,
        "difficulty": props.get("difficulty", "unknown"),
        "view_distance": props.get("view-distance", "unknown"),
        "rcon_enabled": props.get("enable-rcon", "false").lower() == "true",
        "rcon_credential_present": bool(props.get("rcon.password")),
        "max_heap_gib": round(configured_heap, 2) or None,
        "processes": active,
        "listening": listening,
        "warnings": warnings,
    }


def discover_servers(root):
    root = Path(root).expanduser().resolve()
    found = []
    # Deliberately bounded: chosen root plus two levels; never scans the whole disk.
    for folder in [
        root,
        *sorted(p for p in root.glob("*") if p.is_dir()),
        *sorted(p for p in root.glob("*/*") if p.is_dir()),
    ]:
        if (folder / "server.properties").is_file():
            found.append(str(folder))
    return sorted(set(found))[:100]


def memory_info():
    values = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    # Resolve the process cgroup v2 path; account for limits imposed by containers.
    try:
        group = next(
            line.split("::", 1)[1]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        )
        base = Path("/sys/fs/cgroup") / group.lstrip("/")
        for folder in [base, *list(base.parents)]:
            if not folder.is_relative_to("/sys/fs/cgroup"):
                continue
            limit = (folder / "memory.max").read_text().strip()
            used = (folder / "memory.current").read_text().strip()
            if limit.isdigit():
                total = min(total, int(limit))
                available = min(available, max(0, int(limit) - int(used)))
    except (OSError, ValueError, StopIteration):
        pass
    return {"total_gib": round(total / GIB, 2), "available_gib": round(available / GIB, 2)}


def probe_host(root):
    result = {
        "system": platform.system(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cpu_count": os.cpu_count() or 1,
        **memory_info(),
        "disk_free_gib": round(shutil.disk_usage(root).free / GIB, 2),
        "desktop_session_present": bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        ),
    }
    if hasattr(os, "sched_getaffinity"):
        result["cpu_count"] = min(result["cpu_count"], len(os.sched_getaffinity(0)))
    result["wsl"] = "microsoft" in platform.release().lower() or bool(os.environ.get("WSL_INTEROP"))
    result["tools"] = {
        name: shutil.which(name)
        for name in (
            "python3",
            "git",
            "cmake",
            "cc",
            "pkg-config",
            "javac",
            "jar",
            "zstd",
            "kwin_wayland",
            "Xwayland",
            "dbus-run-session",
            "nvcc",
        )
    }
    result["libraries"] = {
        name: ctypes.util.find_library(name) for name in ("X11", "ei", "dbus-1", "GL")
    }
    result["gpus"] = []
    smi = shutil.which("nvidia-smi")
    if not smi and Path("/usr/lib/wsl/lib/nvidia-smi").is_file():
        smi = "/usr/lib/wsl/lib/nvidia-smi"
    if smi:
        try:
            p = subprocess.run(
                [
                    smi,
                    "--query-gpu=index,name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if p.returncode == 0:
                for row in csv.reader(io.StringIO(p.stdout)):
                    index, name, total, free = [x.strip() for x in row]
                    result["gpus"].append(
                        {
                            "index": int(index),
                            "name": name,
                            "total_gib": round(float(total) / 1024, 2),
                            "free_gib": round(float(free) / 1024, 2),
                        }
                    )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    try:
        p = subprocess.run(
            ["kwin_wayland", "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        text = p.stdout + p.stderr
        match = re.search(r"kwin(?:_wayland)?\s+(\d+)\.(\d+)", text, re.I)
        result["kwin_version"] = match.group(0) if match else text.strip()[:160]
        result["kwin_major"] = int(match[1]) if match else None
    except (OSError, subprocess.TimeoutExpired):
        result.update(kwin_version=None, kwin_major=None)
    return result


def recommend(host, server):
    """Heuristic budgets, explicitly not a benchmark or an OOM guarantee."""
    server_heap = server.get("max_heap_gib") or (
        8 if server["loader"] in ("forge", "neoforge", "fabric") else 4
    )
    rss = sum(p.get("rss_gib", 0) for p in server.get("processes", []))
    server_reserve = max(0, server_heap - rss) if server.get("processes") else server_heap
    client_heap = 8 if server["loader"] in ("forge", "neoforge", "fabric") else 4
    os_reserve = 2
    budget = max(0, host["available_gib"] - server_reserve - client_heap - os_reserve)
    gpu = max(host.get("gpus", []), key=lambda g: g["free_gib"], default=None)
    free = gpu["free_gib"] if gpu else 0
    # Includes text+vision, context/compute workspace and >=2GiB game headroom.
    candidates = [
        {"key": "2b", "ram_needed_gib": 4, "gpu_needed_gib": 6.5},
        {"key": "9b", "ram_needed_gib": 10, "gpu_needed_gib": 12},
    ]
    options = []
    for item in candidates:
        fits_ram = budget >= item["ram_needed_gib"]
        gpu_ok = fits_ram and free >= item["gpu_needed_gib"]
        options.append(
            {
                **item,
                "fits_ram": fits_ram,
                "gpu_fit_estimate": gpu_ok,
                "profile": "balanced" if gpu_ok else "cpu",
            }
        )
    # Prefer 9B only when both RAM and full GPU placement have generous headroom.
    choice = next(
        (v for v in reversed(options) if v["fits_ram"] and v["gpu_fit_estimate"]), None
    ) or next((v for v in options if v["fits_ram"]), None)
    return {
        "recommended": choice["key"] if choice else None,
        "profile": choice["profile"] if choice else None,
        "gpu_index": gpu["index"] if gpu and choice and choice["profile"] == "balanced" else None,
        "gpu_layers": 99 if choice and choice["profile"] == "balanced" else 0,
        "vision_gpu": bool(choice and choice["profile"] == "balanced"),
        "server_reserved_gib": round(server_reserve, 2),
        "client_heap_gib": client_heap,
        "os_reserved_gib": os_reserve,
        "model_ram_budget_gib": round(budget, 2),
        "options": options,
        "explanation": "启发式估算，预留服务器增长、客户端和系统内存；GPU预算包含游戏余量。实际占用取决于场景和上下文，不能保证不OOM。",
        "available_models": ["2b", "9b"],
    }


def system_packages(host):
    info = properties("/etc/os-release")
    distro = info.get("ID", "").strip('"')
    like = info.get("ID_LIKE", "").strip('"')
    apt = [
        "kwin-wayland",
        "xwayland",
        "dbus-x11",
        "libei-dev",
        "libdbus-1-dev",
        "libx11-6",
        "libgl1-mesa-dri",
        "mesa-utils",
        "build-essential",
        "pkg-config",
        "default-jdk",
        "python3-venv",
        "python3-pip",
        "git",
        "cmake",
        "zstd",
    ]
    arch = [
        "kwin",
        "xorg-xwayland",
        "dbus",
        "libei",
        "libx11",
        "mesa",
        "mesa-utils",
        "base-devel",
        "pkgconf",
        "jdk-openjdk",
        "python",
        "python-pip",
        "git",
        "cmake",
        "zstd",
    ]
    if distro in ("debian", "ubuntu") or "debian" in like:
        return ["apt-get", "install", "--no-install-recommends", *apt]
    if distro == "arch" or "arch" in like:
        return ["pacman", "-S", "--needed", *arch]
    return None


def plan(root, server, host=None):
    host = host or probe_host(root)
    model = recommend(host, server)
    blockers = []
    warnings = list(server["warnings"])
    if host["system"] != "Linux" or host["architecture"] not in ("x86_64", "amd64"):
        blockers.append("当前自动部署仅支持Linux x86_64")
    if host.get("wsl"):
        blockers.append("WSL尚未完成实机适配，此向导只提供检测报告")
    if not server["supported_version"]:
        blockers.append("服务器版本尚无已验证客户端通道，请核实/显式选择版本")
    if server["online_mode"]:
        blockers.append("在线认证未接入；请使用已授权的离线测试服，不自动关闭原服认证")
    if server["connection"]["port"] in (8789, 8790):
        blockers.append("游戏端口与本工具固定的8789/8790端口冲突，不能在同一地址同时监听")
    if not model["recommended"]:
        blockers.append("预留服务器/客户端资源后，剩余内存不足以推荐现有模型")
    if host["disk_free_gib"] < 35:
        warnings.append("从零下载/转换建议至少35GiB空闲空间；现有模型完整时可能无需重新下载")
    missing = [k for k, v in host["tools"].items() if not v and k not in ("nvcc",)]
    missing_libs = [k for k, v in host["libraries"].items() if not v]
    if host.get("kwin_major") and host["kwin_major"] < 6:
        warnings.append(
            "当前KWin版本过旧，需要支持libei RemoteDesktop接口的KWin6；不要升级整套发行版来静默修复"
        )
    if not host.get("desktop_session_present"):
        warnings.append("未检测到桌面会话；仍会创建专属后台显示，并在启动时验证真实画面和输入连接")
    if not host.get("gpus"):
        warnings.append(
            "未探测到NVIDIA CUDA设备，将推荐CPU模型；游戏仍需可用的硬件或Mesa软件OpenGL"
        )
    return {
        "server": server,
        "host": host,
        "model": model,
        "blockers": blockers,
        "warnings": warnings,
        "missing_tools": missing,
        "missing_libraries": missing_libs,
        "system_install_command": system_packages(host),
        "server_policy": "默认只连接，不改原服、不接管原服进程",
        "memory_policy": "按新实例/world_id独立保存文档记忆",
    }
