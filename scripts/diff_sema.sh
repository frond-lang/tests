#!/usr/bin/env bash
# 1E sema 差分:Rust debug --stage sema vs frondc check,声明前缀逐字节 diff。
#
# 全节契约(片5 起):sema-dump v1 全量逐字节比对 —— 含
# monomorph/trait-defaults/inherited/witness/field-ids/errors/warnings/stats。
# 用法: ./diff_sema.sh <entry.frond>...   (不带参数 = 默认语料)
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    FROND="$(cd ../../Frond/core/target/release && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found at $FROND/core/target/release (build first or set FROND env)" >&2
    exit 2
fi
ROOT="$(cd ../.. && pwd)"
STD="$ROOT/Frond/std"

if [ "$#" -eq 0 ]; then
    set -- \
        "$ROOT/tests/functional/arithmetic/src/Main.frond" \
        "$ROOT/tests/functional/name_resolution/src/Main.frond" \
        "$ROOT/tests/functional/traits/src/Main.frond" \
        "$ROOT/tests/functional/qualified_types/src/Main.frond" \
        "$ROOT/tests/functional/map_field_crosstalk/src/Main.frond" \
        "$ROOT/tests/functional/ctor_name_clash/src/Main.frond"
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT


pass=0
fail=0
for f in "$@"; do
    [ -f "$f" ] || continue
    (cd "$ROOT/Frond/frondc" && timeout 900 "$FROND" run -- checkmany --std "$STD" "$f" \
        > "$tmpdir/mir_raw.txt" 2>/dev/null)
    # checkmany 输出 = @@FRONDC_SPLIT 行 + dump 体(sema 诊断走 stderr,
    # 与 Rust 侧 run_sema_pipeline_or_exit 同款,不进比对);与 diff_load
    # 同款纯 bash 切片。
    awk '/^@@FRONDC_SPLIT_9Q7Z@/{seen=1; next} seen{print}' "$tmpdir/mir_raw.txt" > "$tmpdir/mir.txt"
    "$FROND" debug --stage sema "$f" > "$tmpdir/eng.txt" 2>/dev/null
    if diff -q "$tmpdir/eng.txt" "$tmpdir/mir.txt" > /dev/null; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        echo "FAIL: $f"
        diff "$tmpdir/eng.txt" "$tmpdir/mir.txt" | head -10
    fi
done
echo "sema diff (full dump): $pass passed, $fail failed"
[ "$fail" -eq 0 ]
