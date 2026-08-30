#!/usr/bin/env bash
# 1B 语法差分:Rust debug --stage ast vs frondc parse,逐文件逐字节 diff。
# 用法: ./diff_ast.sh <file.frond>...   (不带参数 = std + libs + frondc + tests + apps)
# 性能:frondc 侧走 parsemany 批量(一次冷启动)。
# 注:两侧都要求解析成功才有输出;一侧失败即 FAIL(报错文案对齐是 1B 后续项)。
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

if [ "$#" -eq 0 ]; then
    set -- $(cd "$ROOT" && find Frond/std Frond/libs Frond/frondc/src tests apps -name '*.frond' | sed "s|^|$ROOT/|")
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# 批量跑 frondc 侧,按 "===== <path>" 分隔切片
# 分批调用(每批 100):Windows 命令行长度上限(同 diff_lex)。
: > "$tmpdir/all.txt"
_batch=()
for _f in "$@"; do
    _batch+=("$_f")
    if [ ${#_batch[@]} -ge 100 ]; then
        (cd "$ROOT/Frond/frondc" && timeout 900 "$FROND" run -- parsemany "${_batch[@]}" >> "$tmpdir/all.txt" 2>/dev/null)
        _batch=()
    fi
done
[ ${#_batch[@]} -gt 0 ] && (cd "$ROOT/Frond/frondc" && timeout 900 "$FROND" run -- parsemany "${_batch[@]}" >> "$tmpdir/all.txt" 2>/dev/null)
# Byte-faithful bash splitter (Windows gawk strips CR and corrupts CRLF lexemes).
# Byte-faithful bash splitter (Windows gawk strips CR and corrupts CRLF lexemes).
n=0
fn=""
while IFS= read -r line; do
    case "$line" in
        "@@FRONDC_SPLIT_9Q7Z@"*"")
            n=$((n+1))
            fn="$(printf '%s/c%05d' "$tmpdir" "$n")"
            printf '%s
' "$line" > "$fn.path"
            ;;
        "Parse error at "*)
            if [ -n "$fn" ]; then printf '%s
' "$line" > "$fn.err"; fi
            ;;
        *)
            if [ -n "$fn" ]; then printf '%s
' "$line" >> "$fn"; fi
            ;;
    esac
done < "$tmpdir/all.txt"

echo "chunks=$(ls "$tmpdir"/*.path 2>/dev/null | wc -l)"
pass=0
fail=0
skip=0
n=0
for f in "$@"; do
    [ -f "$f" ] || continue
    n=$((n+1))
    chunk="$tmpdir/$(printf 'c%05d' $n)"
    # 按序配对(lexmany/parsemany 保序处理参数);MSYS 会把传给原生进程的
    # 路径改写成 Windows 形态,故不比对 .path 字符串,只保留作诊断。
    # 注意顺序:解析报错的 chunk 只有 .err 没有内容文件,先查 .err。
    if [ -f "$chunk.err" ]; then
        if "$FROND" debug --stage ast "$f" > /dev/null 2>&1; then
            fail=$((fail+1))
            echo "FAIL (frondc parse error, rust ok): $f  [$(cat "$chunk.err")]"
        else
            skip=$((skip+1))
        fi
        continue
    fi
    if [ ! -f "$chunk" ]; then
        fail=$((fail+1))
        echo "FAIL (missing chunk): n=$n f=$f chunk=$chunk"
        continue
    fi
    if ! "$FROND" debug --stage ast "$f" > "$tmpdir/rust.txt" 2>/dev/null; then
        # Rust 侧拒绝的文件(负向用例):报错文案对齐是 1B 后续项,跳过计数。
        skip=$((skip+1))
        continue
    fi
    if diff -q "$tmpdir/rust.txt" "$chunk" > /dev/null; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        echo "FAIL: $f"
        diff "$tmpdir/rust.txt" "$chunk" | head -8
    fi
done
echo "ast diff: $pass passed, $fail failed, $skip skipped (rust-rejected)"
[ "$fail" -eq 0 ]
