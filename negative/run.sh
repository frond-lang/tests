#!/usr/bin/env bash
# 负向编译测试 runner：cases/*.kz 必须编译失败且诊断包含 // EXPECT: 子串。
set -u
cd "$(dirname "$0")"

KUZO="${KUZO:-}"
if [ -z "$KUZO" ]; then
    # Resolve an absolute path before any cd — the per-case runs execute in a temp dir.
    KUZO="$(cd "$(dirname "$0")/../../Kuzo/target/release" && pwd)/kuzo.exe"
fi
if [ ! -f "$KUZO" ]; then
    echo "kuzo binary not found at $KUZO (build first or set KUZO env var)" >&2
    exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '[package]\nname = "neg"\nentry = "src/Main.kz"\n\n[build]\noutput_dir = "out"\nopt_level = 2\n' > "$tmp/kuzo.toml"
mkdir -p "$tmp/src"

pass=0
fail=0
for case_file in cases/*.kz; do
    name="$(basename "$case_file" .kz)"
    expect="$(sed -n 's|^// EXPECT: ||p' "$case_file" | head -1)"
    if [ -z "$expect" ]; then
        echo "SKIP: $name (no // EXPECT: line)"
        continue
    fi
    cp "$case_file" "$tmp/src/Main.kz"
    out="$(cd "$tmp" && timeout 60 "$KUZO" run 2>&1)"
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
