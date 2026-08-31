#!/usr/bin/env bash
# 功能测试 runner：遍历 ../functional/*/，每项目 `frond run`，断言输出含 "RESULT: ALL PASSED"。
# 用法: ./run_functional.sh [目录名...]   （不带参数 = 全部）
# 并行: JOBS=N 控制并发（默认 CPU 数、封顶 8；JOBS=1 = 串行）。
#        套件目录互相独立（各自 Root.toml/out/），并行安全；结果按目录序
#        汇总打印（非完成序），判分口径与串行版逐字相同。
# 兼容: 纯 bash 3.2（无 wait -n）；宿主机缺 GNU timeout（macOS 裸机）时
#        内置 bash 兜底，CI 的 macOS runner 不再依赖 brew coreutils。
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

# 基线已知失败（豁免）：当前为空。
# （2026-08-18 清理：edge_ffi_inline 与负向 user_extern_forbidden 断言重复，
#  套件删除；enum_u8_bug/edge_nested_types/str_writeback_bug/edge_tailrec
#  四个旧式套件加 RESULT 判定转正撤豁免。）
# 门禁口径：新增失败 = 失败。豁免清单外的任何 FAIL 都算。
KNOWN_BASELINE_FAIL=""

# ── 平台特化套件：套件目录可放 PLATFORMS 文件（空白分隔：windows/linux/macos，
#    uname 映射 MINGW*/MSYS*/CYGWIN*→windows、Darwin→macos、Linux→linux），
#    当前 OS 不在列 → SKIP（结构性不可过，如 ffi_lib 硬编码 kernel32.dll）。──
host_os=unknown
case "$(uname -s)" in
    Linux*) host_os=linux ;;
    Darwin*) host_os=macos ;;
    MINGW*|MSYS*|CYGWIN*) host_os=windows ;;
esac

# ── 并行度：CPU 数，封顶 8（perf 敏感套件防超卖），JOBS 可覆盖 ──
if [ -z "${JOBS:-}" ]; then
    if command -v nproc >/dev/null 2>&1; then
        JOBS="$(nproc)"
    elif sysctl -n hw.ncpu >/dev/null 2>&1; then
        JOBS="$(sysctl -n hw.ncpu)"
    else
        JOBS=4
    fi
    [ "$JOBS" -gt 8 ] && JOBS=8
fi

# ── timeout 兜底：整秒语义，与本脚本的用法（timeout 300 cmd）一致 ──
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

# ── 筛选目标套件（保持目录序）──
selected=()
skipped=()
for dir in ../functional/*/; do
    name="$(basename "$dir")"
    if [ -f "$dir/PLATFORMS" ] && ! grep -qw "$host_os" "$dir/PLATFORMS"; then
        skipped+=("$name")
        continue
    fi
    if [ "$#" -gt 0 ]; then
        skip=1
        for want in "$@"; do
            [ "$name" = "$want" ] && skip=0
        done
        [ $skip -eq 1 ] && continue
    fi
    selected+=("$name")
done

# ── 并行执行：每套件输出/退出码落 tmpdir，规避 jobs -rp 计数的竞态 ──
# （空数组 + set -u 在 bash 3.2 下展开报错，先显式拦截）
if [ "${#selected[@]}" -eq 0 ]; then
    echo "no suites selected (bad dir name?)" >&2
    exit 1
fi
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

run_one() {
    (
        cd "../functional/$1" && timeout 300 "$FROND" run > "$2.out" 2>&1
    )
    echo $? > "$2.rc"
}

for name in "${selected[@]}"; do
    # 槽位限流：轮询在跑的作业数（$(jobs) 在命令替换里是父 shell 快照）
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do
        sleep 0.2
    done
    run_one "$name" "$tmpdir/$name" &
done
wait

# ── 汇总（目录序，与串行版输出逐字对齐）──
pass=0
fail=0
known=0
failed_names=()
for name in "${selected[@]}"; do
    out="$tmpdir/$name.out"
    ec="$(cat "$tmpdir/$name.rc")"
    is_known=0
    for k in $KNOWN_BASELINE_FAIL; do
        [ "$name" = "$k" ] && is_known=1
    done
    if [ "$ec" -ne 0 ]; then
        if [ $is_known -eq 1 ]; then
            echo "KNOWN-FAIL: $name — exit=$ec (baseline)"
            known=$((known + 1))
        else
            echo "FAIL: $name — exit=$ec"
            tail -5 "$out" | sed 's/^/    /'
            fail=$((fail + 1))
            failed_names+=("$name")
        fi
    elif grep -qF "RESULT: ALL PASSED" "$out"; then
        echo "PASS: $name"
        pass=$((pass + 1))
    elif [ $is_known -eq 1 ]; then
        echo "KNOWN-FAIL: $name — missing 'RESULT: ALL PASSED' (baseline)"
        known=$((known + 1))
    else
        echo "FAIL: $name — missing 'RESULT: ALL PASSED'"
        grep -E "FAIL:|RESULT:" "$out" | head -8 | sed 's/^/    /'
        fail=$((fail + 1))
        failed_names+=("$name")
    fi
done

echo ""
echo "functional tests: $pass passed, $fail failed, $known known-baseline-fail, ${#skipped[@]} platform-skip (JOBS=$JOBS)"
if [ ${#skipped[@]} -gt 0 ]; then
    echo "skipped on $host_os: ${skipped[*]}"
fi
if [ $fail -gt 0 ]; then
    echo "failed: ${failed_names[*]}"
fi
[ $fail -eq 0 ]
