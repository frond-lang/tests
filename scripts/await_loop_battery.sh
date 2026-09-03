#!/usr/bin/env bash
# await_loop 稳定性电池:N 次连跑,任何一次失败即 FAIL。
# 引擎调度稳定性门禁(历史上 Multi 模式挂死/抖动的专项哨兵;M3b 起单一
# 事件循环调度器,同一口径)。
# 用法: ./await_loop_battery.sh [N]    (默认 30;FROND 指定引擎二进制)
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    FROND="$(cd "$(dirname "$0")/../../Frond/core/target/release" && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found at $FROND (build first or set FROND env var)" >&2
    exit 2
fi
N="${1:-30}"

# timeout 兜底(裸 macOS 无 GNU timeout;口径与 run_functional.sh 一致)
if ! command -v timeout >/dev/null 2>&1; then
    timeout() {
        _t=$1; shift
        "$@" &
        _p=$!
        ( sleep "$_t" && kill -9 $_p 2>/dev/null ) &
        _w=$!
        wait $_p; _rc=$?
        kill -9 $_w 2>/dev/null
        wait $_w 2>/dev/null
        return $_rc
    }
fi

cd ../functional/await_loop
pass=0
fail=0
for i in $(seq 1 "$N"); do
    if timeout 90 "$FROND" run >/dev/null 2>&1; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        echo "FAIL: await_loop run #$i"
    fi
done
echo "await_loop x$N: pass=$pass fail=$fail"
[ $fail -eq 0 ]
