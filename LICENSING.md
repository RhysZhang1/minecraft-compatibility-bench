# Licensing

The original code written for Minecraft Compatibility Bench is licensed under the **GNU General Public License, version 3 or (at your option) any later version** (`GPL-3.0-or-later`). See the root `LICENSE` for the full GPL text.

This applies to the project's own compatibility layer, Python and shell tooling, Java agents, native input bridge, tests, configuration templates, and dashboard, except where a file or third-party component carries a separate notice.

The GPL notice does **not** replace the licenses or copyright notices of third-party material:

| Material | Original terms / location |
|---|---|
| `tests/fixtures/protocol/chat_template.jinja` | Apache-2.0 upstream checkpoint template; see `tests/fixtures/README.en.md` |
| Sanitized Minecraft frame fixtures | Applicable upstream game-content terms; no relicensing of Minecraft |
| `vendor/GameScaling/` | Apache-2.0; see `vendor/GameScaling/LICENSE` and `UPSTREAM.md` |
| ASM classes used by the Java agents | BSD-3-Clause; see `THIRD_PARTY_NOTICES/ASM-BSD-3-Clause.txt` |
| libei linked by the native input bridge | MIT; see `THIRD_PARTY_NOTICES/libei-MIT.txt` |
| External llama.cpp source / binaries | Upstream MIT terms; preserve that checkout's LICENSE |
| Model weights, tokenizer/templates and model metadata | Their original upstream terms; not relicensed by this project |
| Minecraft, server/client JARs and mod/resource packs | Their respective upstream terms and EULA; not included in the public source |

Existing third-party notices must accompany redistribution where required. The project's GPL terms apply to its own contributions; third-party portions retain their original terms. Earlier releases retain the notices and permissions already granted with those releases; this change does not revoke them.
