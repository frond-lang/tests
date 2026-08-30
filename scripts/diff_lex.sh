#!/usr/bin/env bash
# 1A 词法差分:Rust debug --stage tokens vs frondc lex,逐文件逐字节 diff。
# 用法: ./diff_lex.sh <file.frond>...   (不带参数 = std + libs + frondc + tests + apps)
# 性能:frondc 侧走 lexmany 批量(一次冷启动),Rust 侧每文件 ~30ms。
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
# 分批调用(每批 100):Windows 命令行长度上限约 32K,453+ 语料一次性
# 传参会 exec 失败(exit 126);分批保序追加,冷启动 ×5 可忽略。
: > "$tmpdir/all.txt"
_batch=()
for _f in "$@"; do
    _batch+=("$_f")
    if [ ${#_batch[@]} -ge 100 ]; then
        (cd "$ROOT/Frond/frondc" && "$FROND" run -- lexmany "${_batch[@]}" >> "$tmpdir/all.txt" 2>/dev/null)
        _batch=()
    fi
done
[ ${#_batch[@]} -gt 0 ] && (cd "$ROOT/Frond/frondc" && "$FROND" run -- lexmany "${_batch[@]}" >> "$tmpdir/all.txt" 2>/dev/null)
# 纯 bash 切片(字节忠实):Windows gawk 按文本模式剥 ,会无声损坏
# 含 CRLF 词素(RawBlock 内嵌 C)的 chunk。
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
        *)
            if [ -n "$fn" ]; then printf '%s
' "$line" >> "$fn"; fi
            ;;
    esac
done < "$tmpdir/all.txt"

pass=0
fail=0
n=0
for f in "$@"; do
    [ -f "$f" ] || continue
    n=$((n+1))
    chunk="$tmpdir/$(printf 'c%05d' $n)"
    # 按序配对(lexmany/parsemany 保序处理参数);MSYS 会把传给原生进程的
    # 路径改写成 Windows 形态,故不比对 .path 字符串,只保留作诊断。
    if [ ! -f "$chunk" ]; then
        fail=$((fail+1))
        echo "FAIL (missing chunk): $f"
        continue
    fi
    if grep -q ' @READFAIL@$' "$chunk.path" 2>/dev/null; then
        fail=$((fail+1))
        echo "FAIL (frondc read error): $f"
        continue
    fi
    "$FROND" debug --stage tokens "$f" > "$tmpdir/rust.txt" 2>/dev/null
    if diff -q "$tmpdir/rust.txt" "$chunk" > /dev/null; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        echo "FAIL: $f"
        diff "$tmpdir/rust.txt" "$chunk" | head -8
    fi
done
echo "lex diff: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
