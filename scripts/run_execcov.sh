#!/usr/bin/env bash
# 执行覆盖门禁：聚合全套件的 EXECCOV 报告，比对基线。
#
# 原理：每个 std 函数若出现在某测试的最终图里（EXECCOV-INV）却从未在任何测试里
# 真正启动过帧（EXECCOV-RUN），就是"从未被执行过的路径"——本项目历史上
# u64(x) 静默 void / [0u8]*len 空数组 / open flags abort / File.remove 假成功
# 全部潜伏在这类路径里。门禁口径：**新增未覆盖 = 失败**；覆盖面扩大提示更新基线。
# （被内联进调用方的函数不会出现在最终图里，天然不算未覆盖；没有被任何测试
# 加载的函数同理——本门禁检测的是"图里有、测试跑了、但它自己从未执行"。）
#
# 用法:
#   ./run_execcov.sh              # 跑全套件并比对基线
#   ./run_execcov.sh --update     # 重新生成基线（覆盖面变化后手动执行）
set -u
cd "$(dirname "$0")"

KUZO="${KUZO:-}"
if [ -z "$KUZO" ]; then
    KUZO="$(cd "$(dirname "$0")/../../Kuzo/target/release" && pwd)/kuzo.exe"
fi
if [ ! -f "$KUZO" ]; then
    echo "kuzo binary not found at $KUZO (build first or set KUZO env var)" >&2
    exit 2
fi

BASELINE="execcov_baseline.txt"
UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# 聚合全套件的 INV（图内存在）与 RUN（真正执行）名字集合
: > "$tmp/inv.txt"
: > "$tmp/run.txt"
for dir in ../functional/*/; do
    # </dev/null: Tty-reading suites must not block on an interactive stdin
    # (same reason run_functional.sh's command substitution is safe).
    out="$(cd "$dir" && KUZO_EXEC_COVERAGE=1 timeout 300 "$KUZO" run </dev/null 2>&1)"
    echo "$out" | grep '^EXECCOV-INV ' | sed 's/^EXECCOV-INV //' >> "$tmp/inv.txt"
    echo "$out" | grep '^EXECCOV-RUN ' | sed 's/^EXECCOV-RUN //' >> "$tmp/run.txt"
done

sort -u "$tmp/inv.txt" -o "$tmp/inv.txt"
sort -u "$tmp/run.txt" -o "$tmp/run.txt"
comm -23 "$tmp/inv.txt" "$tmp/run.txt" > "$tmp/uncovered.txt"

inv_n=$(wc -l < "$tmp/inv.txt" | tr -d ' ')
run_n=$(wc -l < "$tmp/run.txt" | tr -d ' ')
unc_n=$(wc -l < "$tmp/uncovered.txt" | tr -d ' ')
echo "execution coverage: inv=$inv_n ran=$run_n uncovered=$unc_n"

if [ $UPDATE -eq 1 ]; then
    cp "$tmp/uncovered.txt" "$BASELINE"
    echo "baseline updated: $BASELINE ($(wc -l < "$BASELINE" | tr -d ' ') entries)"
    exit 0
fi

if [ ! -f "$BASELINE" ]; then
    echo "no baseline found — run './run_execcov.sh --update' once to create it"
    exit 2
fi

# 门禁：不得出现基线之外的未覆盖 std 函数
new_uncovered="$(comm -13 "$BASELINE" "$tmp/uncovered.txt")"
if [ -n "$new_uncovered" ]; then
    echo "FAIL: newly never-executed std functions (add a test that actually runs them):"
    echo "$new_uncovered" | sed 's/^/    /'
    exit 1
fi

fixed="$(comm -23 "$BASELINE" "$tmp/uncovered.txt")"
if [ -n "$fixed" ]; then
    echo "note: coverage improved; now-covered (consider './run_execcov.sh --update'):"
    echo "$fixed" | sed 's/^/    /'
fi
echo "PASS: no regression in std execution coverage"
