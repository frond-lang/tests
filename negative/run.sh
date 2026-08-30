#!/usr/bin/env bash
# 负向编译测试 runner：cases/*.frond 必须编译失败且诊断包含 // EXPECT: 子串。
set -u
cd "$(dirname "$0")"

FROND="${FROND:-}"
if [ -z "$FROND" ]; then
    # Resolve an absolute path before any cd — the per-case runs execute in a temp dir.
    FROND="$(cd "$(dirname "$0")/../../Frond/core/target/release" && pwd)/frond.exe"
fi
if [ ! -f "$FROND" ]; then
    echo "frond binary not found at $FROND (build first or set FROND env var)" >&2
    exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '[package]\nname = "neg"\nentry = "src/Main.frond"\n\n[build]\noutput_dir = "out"\nopt_level = 2\n' > "$tmp/Root.toml"
mkdir -p "$tmp/src"

pass=0
fail=0
for case_file in cases/*.frond; do
    name="$(basename "$case_file" .frond)"
    expect="$(sed -n 's|^// EXPECT: ||p' "$case_file" | head -1)"
    if [ -z "$expect" ]; then
        echo "SKIP: $name (no // EXPECT: line)"
        continue
    fi
    cp "$case_file" "$tmp/src/Main.frond"
    out="$(cd "$tmp" && timeout 60 "$FROND" run 2>&1)"
    ec=$?
    if [ $ec -eq 0 ]; then
        echo "FAIL: $name — compiled successfully (expected failure)"
        fail=$((fail + 1))
    elif echo "$out" | grep -qF "$expect"; then
        echo "PASS: $name"
        pass=$((pass + 1))
    else
        echo "FAIL: $name — exit=$ec but diagnostic missing '$expect'"
        echo "$out" | head -2 | sed 's/^/    /'
        fail=$((fail + 1))
    fi
done

echo ""
echo "negative tests: $pass passed, $fail failed"
[ $fail -eq 0 ]
