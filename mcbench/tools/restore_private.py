# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebind an already extracted private snapshot to its new directory; no deletion."""

import argparse
import ast
import json
import shutil
from pathlib import Path

from mcbench.paths import ROOT


def path_mapping(metadata, root):
    mapping = {
        metadata["workspace"]: str(root),
        **{origin: str(root / target) for target, origin in metadata["external_exports"].items()},
    }
    # Libraries and assets are exported separately, but launch profiles use their common parent.
    for target, origin in metadata["external_exports"].items():
        if Path(origin).name in ("libraries", "assets") and Path(target).name == Path(origin).name:
            mapping[str(Path(origin).parent)] = str((root / target).parent)
    return mapping


def convert_paths(value, mapping, original_home):
    if isinstance(value, str):
        candidate = original_home + value[1:] if value.startswith("~/") else value
        for source, target in sorted(mapping.items(), key=lambda x: -len(x[0])):
            if candidate == source or candidate.startswith(source + "/"):
                return target + candidate[len(source) :]
        return value
    if isinstance(value, list):
        return [convert_paths(v, mapping, original_home) for v in value]
    if isinstance(value, dict):
        return {k: convert_paths(v, mapping, original_home) for k, v in value.items()}
    return value


def rebind_editable_install(venv: Path, mapping: dict[str, str], original_home: str) -> None:
    """Rebind setuptools' generated package finder as well as its .pth loader.

    An editable install keeps package paths in Python constants, not necessarily
    in the .pth file. Rewrite constants as Python syntax so quoted paths remain valid.
    """

    class Rebind(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.Constant:
            if isinstance(node.value, str):
                return ast.copy_location(
                    ast.Constant(convert_paths(node.value, mapping, original_home)), node
                )
            return node

    for finder in venv.glob(
        "lib/python*/site-packages/__editable___minecraft_compatibility_bench_*_finder.py"
    ):
        tree = Rebind().visit(ast.parse(finder.read_text()))
        finder.write_text(ast.unparse(ast.fix_missing_locations(tree)) + "\n")


def rebind():
    metadata = json.loads((ROOT / "PRIVATE-BACKUP.json").read_text())
    old = metadata["workspace"]
    mapping = path_mapping(metadata, ROOT)

    def convert(value):
        return convert_paths(value, mapping, metadata.get("home", str(Path.home())))

    for name in ["local-settings.json", "local-instances.json", "local-vanilla-servers.json"]:
        p = ROOT / name
        if p.exists():
            shutil.copy2(p, p.with_suffix(".before-rebind.json"))
            p.write_text(
                json.dumps(convert(json.loads(p.read_text())), ensure_ascii=False, indent=2)
            )
            p.chmod(0o600)
    from mcbench import instance_config as ic
    from mcbench import local_environment as env

    # Keep resolved paths private; never write machine paths into public templates.
    p = ROOT / "local-instances.json"
    data = json.loads(p.read_text()) if p.exists() else {"instances": {}}
    for key, profile in ic.settings()["instances"].items():
        data["instances"][key] = convert(profile)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    p.chmod(0o600)
    settings = env.settings()
    llama = ROOT / "external/llama-cpp"
    if llama.exists():
        settings.update(llama_source=str(llama), llama_server=str(llama / "build/bin/llama-server"))
    java = convert(env.java())
    if Path(java).exists():
        settings["java"] = java
    env.save(settings)
    from mcbench.tools import vanilla_servers

    for key, item in vanilla_servers.registry().items():
        folder = Path(item["directory"])
        if folder.is_dir() and folder.resolve().is_relative_to(ROOT):
            vanilla_servers.write_wrappers(folder, key)
    python = ROOT / "external/python-runtime" / metadata.get("python_binary", "bin/python3.11")
    if python.exists() and (ROOT / ".venv").exists():
        for name in {"python", "python3", python.name}:
            p = ROOT / ".venv/bin" / name
            if p.is_symlink():
                p.unlink()
            if not p.exists():
                p.symlink_to(python)
        cfg = ROOT / ".venv/pyvenv.cfg"
        if cfg.exists():
            text = cfg.read_text()
            for source, target in sorted(mapping.items(), key=lambda x: -len(x[0])):
                text = text.replace(source, target)
            text = (
                "\n".join(
                    "home = " + str(python.parent) if line.startswith("home =") else line
                    for line in text.splitlines()
                )
                + "\n"
            )
            cfg.write_text(text)
        for p in (ROOT / ".venv").glob("lib/python*/site-packages/*.pth"):
            text = p.read_text()
            for source, target in sorted(mapping.items(), key=lambda x: -len(x[0])):
                text = text.replace(source, target)
            p.write_text(text)
        rebind_editable_install(ROOT / ".venv", mapping, metadata.get("home", ""))
        for p in (ROOT / ".venv/bin").iterdir():
            if not p.is_file() or p.is_symlink():
                continue
            raw = p.read_bytes()
            if raw.startswith(b"#!") and old.encode() in raw.split(b"\n", 1)[0]:
                p.write_bytes(raw.replace(old.encode(), str(ROOT).encode()))
    print("路径已重绑定。下一步运行 ./setup.sh --doctor；依赖系统显卡驱动与KWin/Xwayland。")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rebind", action="store_true", required=True)
    p.parse_args()
    rebind()
