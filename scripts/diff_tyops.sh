#!/usr/bin/env bash
# 1D 类型系统差分:Rust debug --stage ty-ops vs frondc tyops,逐字节 diff。
# 用法: ./diff_tyops.sh   (固定 battery,无参数)
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    FROND="$(cd ../../Frond/core/target/release && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found at $FROND (build first or set FROND env var)" >&2
    exit 2
fi
ROOT="$(cd ../.. && pwd)"
# ty-ops 不消费文件,但 debug 命令行需要一个可读文件(前置 read_source)。
DUMMY="$ROOT/tests/functional/arithmetic/src/Main.frond"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

"$FROND" debug --stage ty-ops "$DUMMY" > "$tmpdir/rust.txt" 2>/dev/null
(cd "$ROOT/Frond/frondc" && timeout 600 "$FROND" run -- tyops > "$tmpdir/frond.txt" 2>/dev/null)

if diff "$tmpdir/rust.txt" "$tmpdir/frond.txt" > /dev/null; then
    echo "tyops diff: IDENTICAL ($(wc -l < "$tmpdir/rust.txt") lines)"
    exit 0
else
    echo "tyops diff: FAILED"
    diff "$tmpdir/rust.txt" "$tmpdir/frond.txt" | head -10
    exit 1
fi
