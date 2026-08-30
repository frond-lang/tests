#!/usr/bin/env python3
"""Generate Frond/frondc/src/StdPaths.frond from core/src/module/StdlibEmbed.rs.

The order is load-bearing: the Frond-side loader mirrors the Rust
sibling-symbol fallback (Loader.rs step 5b), which iterates BUILTIN_FILES
then STD_FILES in declaration order — first hit wins. Regenerate whenever
StdlibEmbed.rs changes:

    python tests/scripts/gen_std_paths.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Frond" / "core" / "src" / "module" / "StdlibEmbed.rs"
DST = ROOT / "Frond" / "frondc" / "src" / "module" / "StdPaths.frond"


def extract(name: str, text: str) -> list[str]:
    m = re.search(rf"pub const {name}: &\[StdlibFile\] = &\[(.*?)\];", text, re.S)
    if m is None:
        sys.exit(f"error: {name} block not found in {SRC}")
    return re.findall(r'\("([^"]+)",\s*include_str!', m.group(1))


def block(paths: list[str]) -> str:
    return ",\n".join(f'    "{p}"' for p in paths)


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    builtin = extract("BUILTIN_FILES", text)
    std = extract("STD_FILES", text)
    if not builtin or not std:
        sys.exit("error: empty manifest extracted")

    content = (
        "// StdPaths.frond — stdlib 有序清单(1C 自动生成,勿手改)。\n"
        "//\n"
        "// 顺序承重:Rust 侧 Loader.rs 的兄弟符号回退(第 5b 步)按 BUILTIN_FILES\n"
        "// → STD_FILES 的声明序迭代,先命中者胜;本清单必须与 StdlibEmbed.rs 同序。\n"
        "// 再生成:python tests/scripts/gen_std_paths.py(增删 std 文件后必跑)。\n"
        "\n"
        "pub fun builtin_paths(): str[] {\n"
        "    [\n"
        f"{block(builtin)}\n"
        "    ]\n"
        "}\n"
        "\n"
        "pub fun std_paths(): str[] {\n"
        "    [\n"
        f"{block(std)}\n"
        "    ]\n"
        "}\n"
    )

    if DST.exists() and DST.read_text(encoding="utf-8") == content:
        print(f"up to date: {DST.relative_to(ROOT)} ({len(builtin)} builtin + {len(std)} std)")
        return
    DST.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote: {DST.relative_to(ROOT)} ({len(builtin)} builtin + {len(std)} std)")


if __name__ == "__main__":
    main()
