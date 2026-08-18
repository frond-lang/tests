#!/usr/bin/env bash
# 功能测试 runner：遍历 ../functional/*/，每项目 `frond run`，断言输出含 "RESULT: ALL PASSED"。
# 用法: ./run_functional.sh [目录名...]   （不带参数 = 全部）
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    FROND="$(cd "$(dirname "$0")/../../Frond/target/release" && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found at $FROND (build first or set FROND env var)" >&2
    exit 2
fi

# 基线已知失败（豁免）：当前为空。
# （2026-08-18 清理：edge_ffi_inline 与负向 user_extern_forbidden 断言重复，
#  套件删除；enum_u8_bug/edge_nested_types/str_writeback_bug/edge_tailrec
#  四个旧式套件加 RESULT 判定转正撤豁免。）
# 门禁口径：新增失败 = 失败。豁免清单外的任何 FAIL 都算。
KNOWN_BASELINE_FAIL=""

pass=0
fail=0
known=0
failed_names=()
for dir in ../functional/*/; do
    name="$(basename "$dir")"
    if [ "$#" -gt 0 ]; then
        skip=1
        for want in "$@"; do
            [ "$name" = "$want" ] && skip=0
        done
        [ $skip -eq 1 ] && continue
    fi
    out="$(cd "$dir" && timeout 300 "$FROND" run 2>&1)"
    ec=$?
    is_known=0
    for k in $KNOWN_BASELINE_FAIL; do
        [ "$name" = "$k" ] && is_known=1
    done
    if [ $ec -ne 0 ]; then
        if [ $is_known -eq 1 ]; then
            echo "KNOWN-FAIL: $name — exit=$ec (baseline)"
            known=$((known + 1))
        else
            echo "FAIL: $name — exit=$ec"
            echo "$out" | tail -5 | sed 's/^/    /'
            fail=$((fail + 1))
            failed_names+=("$name")
        fi
    elif echo "$out" | grep -qF "RESULT: ALL PASSED"; then
        echo "PASS: $name"
        pass=$((pass + 1))
    elif [ $is_known -eq 1 ]; then
        echo "KNOWN-FAIL: $name — missing 'RESULT: ALL PASSED' (baseline)"
        known=$((known + 1))
    else
        echo "FAIL: $name — missing 'RESULT: ALL PASSED'"
        echo "$out" | grep -E "FAIL:|RESULT:" | head -8 | sed 's/^/    /'
        fail=$((fail + 1))
        failed_names+=("$name")
    fi
done

echo ""
echo "functional tests: $pass passed, $fail failed, $known known-baseline-fail"
if [ $fail -gt 0 ]; then
    echo "failed: ${failed_names[*]}"
fi
[ $fail -eq 0 ]
