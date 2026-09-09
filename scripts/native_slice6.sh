#!/usr/bin/env bash
# Stage 2 切片 4 native 验收(BOOTSTRAP_PLAN 附九):
#   frondc native --run <case>.frond → lower LLVM .obj(多 ctor ADT =
#   ptr → per-ctor struct {i64 tag, fields};T? = ptr → {i64, T};
#   match 全模式族 CPS 双续体 + guard)→ 资产 lld 链接 → 跑原生产物
#   → 断言退出码 == 用例头 `// EXPECT-EXIT <n>`。
# 工具链资产:$FRONDC_TOOLCHAIN > tests/functional/llvm_probe/assets/
# toolchain(CI 预取布局,ci.yml setup-frond 已就位)。
# 语料:tests/fixtures/native_slice6/cases/*.frond(ADT 枚举/带字段/
#   nullable/全模式族/聚合互嵌/深度嵌套)。
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    FROND="$(cd ../../Frond/core/target/release && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found (build first or set FROND env)" >&2
    exit 2
fi
ROOT="$(cd ../.. && pwd)"
STD="$ROOT/Frond/std"
TC="${FRONDC_TOOLCHAIN:-$ROOT/tests/functional/llvm_probe/assets/toolchain}"
CASES="$ROOT/tests/fixtures/native_slice6/cases"

if [ ! -d "$TC/lib" ]; then
    echo "toolchain assets not found at $TC (set FRONDC_TOOLCHAIN or prefetch llvm_probe assets)" >&2
    exit 2
fi

pass=0
fail=0
for f in "$CASES"/*.frond "$CASES"/*/src/Main.frond; do
    [ -f "$f" ] || continue
    expected="$(sed -n 's|^// EXPECT-EXIT ||p' "$f" | head -1)"
    if [[ "$f" == */src/Main.frond ]]; then
        name="$(basename "$(dirname "$(dirname "$f")")")"
    else
        name="$(basename "$f")"
    fi
    if [ -z "$expected" ]; then
        echo "SKIP (no EXPECT-EXIT): $name"
        continue
    fi
    out="$(cd "$ROOT/Frond/frondc" && FRONDC_TOOLCHAIN="$TC" timeout 900 "$FROND" run -- native --run --std "$STD" "$f" 2>&1)"
    rc_line="$(printf '%s\n' "$out" | sed -n 's|^native: run .* -> exit ||p' | tail -1)"
    # 产物清理(落 frondc CWD:<base>.o / <base>.exe)。
    base="${name%.frond}"
    rm -f "$ROOT/Frond/frondc/$base.o" "$ROOT/Frond/frondc/$base.exe" "$ROOT/Frond/frondc/$base"
    if [ -z "$rc_line" ]; then
        echo "FAIL $name: no run result"
        printf '%s\n' "$out" | sed -n '1,12p'
        fail=$((fail + 1))
    elif [ "$rc_line" = "$expected" ]; then
        echo "PASS $name (exit $rc_line)"
        pass=$((pass + 1))
    else
        echo "FAIL $name: expected $expected, got $rc_line"
        printf '%s\n' "$out" | sed -n '1,12p'
        fail=$((fail + 1))
    fi
done
echo "native_slice6: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
