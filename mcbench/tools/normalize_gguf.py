# SPDX-License-Identifier: GPL-3.0-or-later
"""Normalize absent-MTP metadata, without changing a single tensor byte."""

import hashlib
import json
import struct

from mcbench.paths import ROOT

SRC = ROOT / "models/GameScaling-9B-S1-GGUF/GameScaling-9B-S1.Q4_K_M.gguf"
DST = SRC.with_name("GameScaling-9B-S1.Q4_K_M.compat.gguf")


def inspect(path):
    f = path.open("rb")
    assert f.read(4) == b"GGUF"
    version, nt, nk = struct.unpack("<IQQ", f.read(20))
    assert version == 3

    def string():
        n = struct.unpack("<Q", f.read(8))[0]
        return f.read(n).decode("utf8")

    fmts = {
        0: "B",
        1: "b",
        2: "H",
        3: "h",
        4: "I",
        5: "i",
        6: "f",
        7: "?",
        10: "Q",
        11: "q",
        12: "d",
    }

    def value(t, keep=False):
        if t == 8:
            return string()
        if t == 9:
            sub, n = struct.unpack("<IQ", f.read(12))
            if sub in fmts:
                f.seek(n * struct.calcsize("<" + fmts[sub]), 1)
            else:
                for _ in range(n):
                    value(sub)
            return None
        fmt = "<" + fmts[t]
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]

    fields = {}
    alignment = 32
    for _ in range(nk):
        key = string()
        typ = struct.unpack("<I", f.read(4))[0]
        offset = f.tell()
        val = value(typ)
        if key in ("qwen35.block_count", "qwen35.nextn_predict_layers"):
            fields[key] = (offset, typ, val)
        if key == "general.alignment":
            alignment = val
    names = []
    for _ in range(nt):
        names.append(string())
        nd = struct.unpack("<I", f.read(4))[0]
        f.seek(8 * nd + 4 + 8, 1)
    pos = f.tell()
    f.close()
    return fields, names, (pos + alignment - 1) // alignment * alignment


def digest(path, start=0):
    h = hashlib.sha256()
    with path.open("rb") as f:
        f.seek(start)
        for b in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def main():
    expected = json.loads((ROOT / "models-checksums.json").read_text())[SRC.name]["sha256"]
    if digest(SRC) != expected:
        raise ValueError("原始9B模型SHA256不一致；未修改兼容副本")
    fields, names, data_start = inspect(SRC)
    actual = max(int(n.split(".")[1]) for n in names if n.startswith("blk.")) + 1
    assert (
        actual == 32
        and fields["qwen35.block_count"][2] == 33
        and fields["qwen35.nextn_predict_layers"][2] == 1
    )
    assert not any(n.startswith("blk.32.") for n in names)
    temporary = DST.with_suffix(".partial.gguf")
    # Publish only after tensor validation, so an interrupted edit cannot be reused.
    __import__("subprocess").run(["cp", "--reflink=auto", str(SRC), str(temporary)], check=True)
    edits = []
    with temporary.open("r+b") as f:
        for key, new in [("qwen35.block_count", 32), ("qwen35.nextn_predict_layers", 0)]:
            offset, typ, old = fields[key]
            assert typ == 4
            f.seek(offset)
            f.write(struct.pack("<I", new))
            edits.append({"key": key, "offset": offset, "old": old, "new": new})
        # Preserve the stale 33-entry array as unused metadata. The engine then
        # derives the identical 32-layer pattern from full_attention_interval=4.
        oldkey = b"qwen35.attention.recurrent_layers"
        newkey = b"qwen35.attention.recurrent_unused"
        assert len(oldkey) == len(newkey)
        with SRC.open("rb") as original:
            header = original.read(data_start)
        offset = header.index(oldkey)
        value_offset = offset + len(oldkey) + 4
        subtype, count = struct.unpack_from("<IQ", header, value_offset)
        assert subtype == 7 and count == 33
        pattern = list(header[value_offset + 12 : value_offset + 12 + 32])
        assert pattern == [int((i + 1) % 4 != 0) for i in range(32)]
        f.seek(offset)
        f.write(newkey)
        edits.append(
            {
                "key": oldkey.decode(),
                "offset": offset,
                "rename": newkey.decode(),
                "reason": "derive main-layer attention pattern from interval=4",
            }
        )
    tensor_hash = digest(SRC, data_start)
    assert tensor_hash == digest(temporary, data_start)
    temporary.replace(DST)
    record = {
        "source": SRC.name,
        "output": DST.name,
        "edits": edits,
        "tensor_data_start": data_start,
        "tensor_sha256_unchanged": tensor_hash,
        "output_sha256": digest(DST),
    }
    (ROOT / "gguf-normalization.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
