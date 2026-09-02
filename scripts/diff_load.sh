#!/usr/bin/env bash
# 1C 模块加载差分:Rust debug --stage load vs frondc loaddeps,逐文件逐字节 diff。
# 用法: ./diff_load.sh <entry.frond>...   (不带参数 = 默认语料)
# 性能:frondc 侧走 loadmany 批量(一次冷启动);全语料 ≈15-25 分钟,
#       建议后台跑。std 根显式传 --std(避免 CWD 探测抖动)。
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
STD="$ROOT/Frond/std"

if [ "$#" -eq 0 ]; then
    set -- \
        "$ROOT/tests/functional/arithmetic/src/Main.frond" \
        "$ROOT/tests/functional/name_resolution/src/Main.frond" \
        "$ROOT/tests/functional/expressiveness/src/Main.frond" \
        "$ROOT/tests/functional/loaddeps/src/Main.frond" \
        "$ROOT/apps/checksum/src/Main.frond" \
        "$ROOT/apps/editor/src/Main.frond" \
        "$ROOT/apps/llvmfetch/src/Main.frond" \
        "$ROOT/Frond/frondc/src/Main.frond" \
        "$ROOT/Frond/std/io/Fs.frond" \
        "$ROOT/tests/fixtures/loaddeps_neg/missing/src/Main.frond" \
        "$ROOT/tests/fixtures/loaddeps_neg/circular/src/Main.frond" \
        "$ROOT/tests/fixtures/loaddeps_neg/badmanifest/src/Main.frond"
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# 批量跑 frondc 侧(loadmany),按 "@@FRONDC_SPLIT_9Q7Z@@" 分隔切片。
# 纯 bash 切分(Windows gawk 文本模式剥 \r 会损坏 CRLF)。
(cd "$ROOT/Frond/frondc" && timeout 2400 "$FROND" run -- loadmany --std "$STD" "$@" \
    > "$tmpdir/all.txt" 2> "$tmpdir/frondc.err")
n=0
fn=""
while IFS= read -r line; do
    case "$line" in
        "@@FRONDC_SPLIT_9Q7Z@"*"")
            n=$((n+1))
            fn="$(printf '%s/c%05d' "$tmpdir" "$n")"
            printf '%s\n' "$line" > "$fn.path"
            ;;
        *)
            if [ -n "$fn" ]; then printf '%s\n' "$line" >> "$fn"; fi
            ;;
    esac
done < "$tmpdir/all.txt"

echo "chunks=$(ls "$tmpdir"/*.path 2>/dev/null | wc -l)"
pass=0
fail=0
n=0
for f in "$@"; do
    [ -f "$f" ] || continue
    n=$((n+1))
    chunk="$tmpdir/$(printf 'c%05d' $n)"
    if [ ! -f "$chunk" ]; then
        fail=$((fail+1))
        echo "FAIL (missing chunk): n=$n f=$f"
        continue
    fi
    "$FROND" debug --stage load "$f" > "$tmpdir/rust.txt" 2>/dev/null
    if diff -q "$tmpdir/rust.txt" "$chunk" > /dev/null; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        echo "FAIL: $f"
        diff "$tmpdir/rust.txt" "$chunk" | head -10
    fi
done
echo "load diff: $pass passed, $fail failed"
# 崩溃取证:frondc 侧 stderr 落盘,失败时倾倒尾部(此前 2>/dev/null 把
# panic 吞掉,池路径崩溃无迹可循)。
if [ -s "$tmpdir/frondc.err" ] && [ "$fail" -ne 0 ]; then
    echo "---- frondc stderr (tail) ----"
    tail -40 "$tmpdir/frondc.err"
fi
[ "$fail" -eq 0 ]
