#!/usr/bin/env bash
# 性能基准 runner：遍历 ../perf/*/，每项目跑 N 次取每个 "elapsed: N ms" 的中位数。
# 用法: ./run_perf.sh [N]    （默认 N=5）
# 输出: 每项目每段计时的中位数（ms），便于前后对比。
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    FROND="$(cd "$(dirname "$0")/../../Kuzo/target/release" && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found at $FROND (build first or set FROND env var)" >&2
    exit 2
fi

N="${1:-5}"

median() {
    # 输入: 每行一个数字；输出: 中位数
    sort -n | awk '{a[NR]=$1} END {if (NR % 2 == 1) print a[(NR+1)/2]; else print (a[NR/2]+a[NR/2+1])/2}'
}

for dir in ../perf/*/; do
    name="$(basename "$dir")"
    # 收集每次运行的全部 "elapsed: N ms" 行（多段计时按出现顺序配对取中位）
    runs=()
    for i in $(seq 1 "$N"); do
        out="$(cd "$dir" && timeout 600 "$FROND" run 2>&1)"
        if [ $? -ne 0 ]; then
            echo "ERROR: $name run #$i failed"
            continue
        fi
        idx=0
        while IFS= read -r line; do
            ms="$(echo "$line" | sed -n 's/.*elapsed: \([0-9.]*\) ms.*/\1/p')"
            [ -z "$ms" ] && continue
            runs[$idx]="${runs[$idx]:-} $ms"
            idx=$((idx + 1))
        done <<< "$(echo "$out" | grep -F "elapsed:")"
    done
    # 输出各段中位数
    seg=0
    line_out=""
    while :; do
        vals="${runs[$seg]:-}"
        [ -z "$vals" ] && break
        med="$(echo $vals | tr ' ' '\n' | median)"
        line_out="$line_out  seg${seg}=${med}ms"
        seg=$((seg + 1))
    done
    echo "$name:$line_out"
done
