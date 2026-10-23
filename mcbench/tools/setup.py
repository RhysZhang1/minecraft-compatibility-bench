# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive, project-local setup. Inspection never downloads or changes model."""

import argparse
import ctypes.util
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from mcbench import instance_config as ic
from mcbench import local_environment as env
from mcbench import model_config as model_config
from mcbench.paths import ROOT

PYTHON = ROOT / ".venv/bin/python"


def run(args):
    return subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def prompt(message, default=""):
    return input(message + (" [" + str(default) + "]" if default else "") + ": ").strip() or str(
        default
    )


def yes(message):
    return prompt(message + " [y/N]").lower() == "y"


def environment():
    print("仅在本项目创建Python环境；不改系统Python、Java或显卡驱动。")
    for key, variable, current in [
        ("java", "MINECRAFT_JAVA_BIN", env.java()),
        ("llama_source", "LLAMA_CPP_SOURCE", env.llama_source()),
        ("llama_server", "LLAMA_SERVER_BIN", env.llama_server()),
    ]:
        chosen = Path(prompt(key, current)).expanduser().resolve()
        if not chosen.exists():
            print("路径尚不存在：" + str(chosen))
        env.save({key: str(chosen)})
    print("运行依赖：requirements.txt；下载工具：requirements-hub.txt；转换依赖另行选择。")
    if yes("创建/补齐本地Python运行环境和下载工具？"):
        uv = shutil.which("uv")
        if not PYTHON.exists():
            if uv:
                run([uv, "venv", "--python", "3.11", ROOT / ".venv"])
            else:
                run([sys.executable, "-m", "venv", ROOT / ".venv"])
        install = (
            [uv, "pip", "install", "--python", PYTHON] if uv else [PYTHON, "-m", "pip", "install"]
        )
        run(install + ["-e", str(ROOT) + "[hub]"])
    if yes("补齐2B本地转换依赖（会占用额外空间）？"):
        if not PYTHON.exists():
            raise ValueError("请先创建本地Python环境")
        uv = shutil.which("uv")
        install = (
            [uv, "pip", "install", "--python", PYTHON] if uv else [PYTHON, "-m", "pip", "install"]
        )
        run(install + ["-r", ROOT / "requirements-conversion.txt"])
    if yes("准备只读状态采集器的ASM编译依赖？"):
        run([sys.executable, ROOT / "scripts/download_sdk.py"])


def doctor(full=False):
    result = {
        "system": platform.system(),
        "architecture": platform.machine(),
        "instance": ic.selected(),
        "backend": ic.config()["backend"] if ic.selected() else None,
        "selected_model": model_config.selected(),
        "paths": {},
        "tools": {},
        "models": {},
    }
    paths = [
        ("java", env.java()),
        ("llama_server", env.llama_server()),
        ("llama_source", env.llama_source()),
    ]
    if ic.selected():
        paths += [
            ("java", ic.java()),
            ("client", ic.client_directory()),
            ("server", ic.server_directory()),
            ("libraries", ic.library_root() / "libraries"),
        ]
    else:
        result["setup_required"] = "Run ./setup.sh (option 6), or --server-dir /path/to/server."
    for name, value in paths:
        result["paths"][name] = {"path": str(value), "exists": Path(value).exists()}
    for tool in [
        "python3",
        "uv",
        "javac",
        "jar",
        "zstd",
        "git",
        "cmake",
        "ninja",
        "nvcc",
        "nvidia-smi",
        "kwin_wayland",
        "Xwayland",
        "dbus-run-session",
        "cc",
        "pkg-config",
    ]:
        result["tools"][tool] = shutil.which(tool)
    result["native_libraries"] = {
        name: ctypes.util.find_library(name) for name in ("X11", "ei", "dbus-1", "GL")
    }
    result["python_environment"] = {"exists": PYTHON.exists()}
    if PYTHON.exists():
        p = subprocess.run(
            [str(PYTHON), "-c", "import PIL,requests,psutil,jinja2"], capture_output=True, text=True
        )
        result["python_environment"].update(imports_ok=p.returncode == 0, error=p.stderr.strip())
    for key in model_config.settings()["models"]:
        conf = model_config.config(key)
        files = {}
        for path, digest in model_config.expected(conf).items():
            info = {"exists": path.is_file(), "bytes": path.stat().st_size if path.is_file() else 0}
            if full and path.is_file():
                h = hashlib.sha256()
                with path.open("rb") as f:
                    for b in iter(lambda: f.read(16 * 1024 * 1024), b""):
                        h.update(b)
                info["sha256"] = h.hexdigest()
                info["valid"] = h.hexdigest() == digest
            files[str(path.relative_to(ROOT))] = info
        result["models"][key] = files
    if shutil.which("nvidia-smi"):
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        )
        result["gpu"] = p.stdout.strip() if p.returncode == 0 else p.stderr.strip()
    result["free_gib"] = round(shutil.disk_usage(ROOT).free / 2**30, 1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def models():
    doctor()
    key = prompt("处理哪个模型（2b/9b）", "2b")
    if key not in ("2b", "9b"):
        raise ValueError("不支持的模型")
    print(
        "模型来源、固定revision与SHA256保存在download_models.sh及models-*-manifest.json。当前选中模型不会改变。"
    )
    if yes("下载/续传这个模型？"):
        run(["bash", ROOT / "scripts/download_models.sh", key])
    if yes("进行本地转换/兼容处理并校验？"):
        run(
            [
                PYTHON,
                ROOT / ("scripts/prepare_2b.py" if key == "2b" else "scripts/normalize_gguf.py"),
            ]
        )
    if yes("将默认模型切换为" + key + "（已运行服务需先停止）？"):
        from mcbench.tools import manage

        if manage.owned("model"):
            raise ValueError("先运行stop.sh再切换模型")
        model_config.select(key)


def vanilla():
    from mcbench.tools import instances

    instances.idle()
    version = prompt("版本（1.7.10 / 1.20.1 / 1.21.1 / 26.3）", "1.21.1")
    if version not in ("1.7.10", "1.20.1", "1.21.1", "26.3"):
        raise ValueError("此版本尚未进入本机测试清单，请先查看docs/PORTABILITY.md")
    key = "vanilla-" + version.replace(".", "-")
    major = {"1.7.10": 8, "1.20.1": 17, "1.21.1": 21, "26.3": 25}[version]
    base = prompt("独立服务器目录的父目录", ROOT / "instances/vanilla-servers")
    port = int(
        prompt(
            "游戏端口", {"1.7.10": 25566, "1.20.1": 25569, "1.21.1": 25568, "26.3": 25567}[version]
        )
    )
    rcon = int(prompt("本地命令端口", port + 20))
    eula = prompt("已有接受记录的eula.txt路径（可留空，之后由你阅读条款并配置）")
    from mcbench.tools import vanilla_servers as vs

    if version in vs.registry():
        existing = vs.registry()[version]
        print(
            "已登记服务器："
            + existing["directory"]
            + "；端口 "
            + str(existing["port"])
            + "。保留原世界，不使用新目录/端口。"
        )
        if not yes("复用该服务器并补齐官方客户端/Java？"):
            return
    print("将下载官方客户端/库/资源/服务器/Java，仅在项目及上面的服务器父目录内写入；不读取账号。")
    if not yes("开始安装？"):
        return
    run([sys.executable, ROOT / "scripts/install_vanilla_client.py", version])
    run([sys.executable, ROOT / "scripts/install_java.py", major])
    runtime = str(ROOT / "instances/java" / str(major) / "bin/java")
    if version not in vs.registry():
        vs.create(version, base, port, rcon, eula_source=eula or None, java=runtime)
    item = vs.registry()[version]
    profile = ic.settings()["instances"].get(key) or ic.template(
        key,
        {
            "JAVA_BIN": runtime,
            "CLIENT_DIRECTORY": "instances/vanilla-" + version + "-client",
            "LIBRARIES_ROOT": "instances/vanilla-runtime",
            "SERVER_DIRECTORY": item["directory"],
        },
    )
    if eula and not (Path(item["directory"]) / "eula.txt").exists():
        shutil.copy2(vs.require_eula(eula), Path(item["directory"]) / "eula.txt")
    profile["server"]["directory"] = item["directory"]
    profile["connection"]["port"] = item["port"]
    profile["server"]["rcon_port"] = item["rcon_port"]
    profile["java"] = "instances/java/" + str(major) + "/bin/java"
    values = vs.registry()
    values[version]["java"] = str(ROOT / profile["java"])
    vs.REGISTRY.write_text(json.dumps(values, indent=2))
    vs.REGISTRY.chmod(0o600)
    p = ROOT / "local-instances.json"
    data = json.loads(p.read_text()) if p.exists() else {"instances": {}}
    data["instances"][key] = profile
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    p.chmod(0o600)
    ic.select(key)
    print("安装完成：./start.sh --instance " + key + " --paused")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--doctor", action="store_true")
    p.add_argument("--verify-models", action="store_true")
    p.add_argument("--server-dir", help="已有服务器目录，进入检测/推荐/添加向导")
    p.add_argument("--inspect-server", help="只读检测服务器并推荐部署方案")
    p.add_argument("--version", help="元数据无法识别时指定MC基础版本")
    a = p.parse_args()
    if a.server_dir or a.inspect_server:
        from mcbench import deployment as deployment
        from mcbench.tools import deploy_server

        try:
            if a.inspect_server:
                print(
                    json.dumps(
                        deployment.plan(
                            ROOT, deployment.inspect_server(a.inspect_server, a.version)
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                deploy_server.wizard(a.server_dir, a.version)
            return 0
        except (
            ValueError,
            OSError,
            subprocess.CalledProcessError,
            EOFError,
            KeyboardInterrupt,
        ) as exc:
            print("未完成：" + (str(exc) or "已取消"), file=sys.stderr)
            return 1
    if a.doctor or a.verify_models:
        doctor(a.verify_models)
        return
    while True:
        print(
            "\nMinecraft × GameScaling 本地配置\n1 检测环境/模型\n2 配置环境与依赖\n3 检测、下载、准备模型\n4 列出/切换实例\n5 导入兼容客户端和服务器\n6 安装指定版本原版客户端、服务器与Java\n7 备份（源码或完整私有备份）\n8 下载并编译llama.cpp（可选）\n9 为已有服务器检测环境、推荐模型并添加AI\n0 退出"
        )
        try:
            choice = prompt("选择", "1")
            if choice == "0":
                return
            if choice == "1":
                doctor(yes("同时完整校验模型文件？"))
            elif choice == "2":
                environment()
            elif choice == "3":
                models()
            elif choice == "4":
                run([sys.executable, ROOT / "scripts/instances.py", "list"])
                key = prompt("切换到哪个实例（回车保持）")
                if key:
                    run([sys.executable, ROOT / "scripts/instances.py", "select", key])
            elif choice == "5":
                run([sys.executable, ROOT / "scripts/instances.py", "import"])
            elif choice == "6":
                vanilla()
            elif choice == "7":
                full = yes("完整备份包含模型、世界与私有记忆；请先stop.sh。创建完整备份？")
                run([sys.executable, ROOT / "scripts/backup.py"] + (["--full"] if full else []))
            elif choice == "8":
                destination = prompt("新建llama.cpp目录", ROOT / "engines/llama.cpp")
                cuda = yes("启用CUDA（需要已安装CUDA编译工具）？")
                jobs = prompt("编译并发数", "2")
                if yes("从官方仓库下载固定版本并在上面的新目录编译？"):
                    run(
                        [
                            sys.executable,
                            ROOT / "scripts/build_engine.py",
                            destination,
                            "--jobs",
                            jobs,
                        ]
                        + ([] if cuda else ["--cpu"])
                    )
            elif choice == "9":
                from mcbench.tools import deploy_server

                deploy_server.wizard()
            else:
                print("无效选择")
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            print("未完成：" + str(exc))


if __name__ == "__main__":
    sys.exit(main())
