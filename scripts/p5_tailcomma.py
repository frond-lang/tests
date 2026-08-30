# p5_tailcomma.py — 修「语句位 match 的尾逗号」(复用 4b 轮算法)。
import io, re, sys

def fix(path):
    lines = io.open(path, encoding="utf-8").read().split("\n")
    stack = []
    changed = 0
    out = []
    MATCH_RE = re.compile(r"^\s*match\b.*\{\s*$")
    LINE_CAND = re.compile(r"^(\s*)\},?\s*$")
    for raw in lines:
        line = raw
        stripped = line.strip()
        is_comment = stripped.startswith("//")
        opens = 0 if is_comment else line.count("{")
        closes = 0 if is_comment else line.count("}")
        if not is_comment and MATCH_RE.match(line):
            stack.append("match")
            out.append(line)
            continue
        m = LINE_CAND.match(line)
        if m and not is_comment and stack:
            kind = stack[-1]
            if closes >= 1:
                stack.pop()
            if kind == "match" and stripped.startswith("},"):
                line = line.replace("},", "}", 1)
                changed += 1
            out.append(line)
            continue
        if not is_comment:
            delta = opens - closes
            if delta > 0:
                for _ in range(delta):
                    stack.append("block")
            elif delta < 0:
                for _ in range(-delta):
                    if stack:
                        stack.pop()
        out.append(line)
    if changed:
        io.open(path, "w", encoding="utf-8", newline="").write("\n".join(out))
    print(path.split("\\")[-1], "fixed", changed)

for p in sys.argv[1:]:
    fix(p)
