#!/usr/bin/env bash
# Stage 2 切片 6e native 验收(std 泛型 List/Map):
#   std 模块进收集面(全量原型注册,可达性发射只编被调者)+
#   命名空间接收者方法调用路由(实例分派)+ inst_param_ty TGeneric
#   多参泛型族 + 泛型聚合布局/字段访问代换(agg_kind/ty_key/
#   record_layout_h/subst_ty)+ 泛型构造器实参反推(infer_ctor_args
#   → overlay)+ 泛型类型方法实例(meth_inst_rows + Mono.
#   replay_method_body this 绑定重放)+ rt 原语(__mem_copy 族/
#   __hash_key_str/__fnv1a_bytes)+ type_name/bytes intrinsic +
#   StrInterp + 动态数组 fill。
# 语料:tests/fixtures/native_slice6e/cases(47-54)。
# 切片 6f 增补:keys()/values()(零参工厂使用驱动绑定:List.empty()
#   的 T 经 out.push 实参闭包)+ i64 键(非 str 哈希路径)。
# 已知留洞:entries() = HashIterator builtin(后续切片)。
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
CASES="$ROOT/tests/fixtures/native_slice6e/cases"

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
echo "slice6e: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
