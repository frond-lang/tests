# opt_join_autofix.py — T→T? 赋值行机械改写(if-join),直至无此类错。
# 用法: python opt_join_autofix.py <rounds>
import io, re, subprocess, sys

FROND = r"F:\Projects\Rust\frond-lang\Frond\core\target\release\frond.exe"
CWD = r"F:\Projects\Rust\frond-lang\Frond\frondc"
PROBE = r"C:\Users\99671\AppData\Local\Temp\p4b\T1.frond"
SEMA_DIR = CWD + r"\src\sema"

ARM_RE = re.compile(r"^(\s*[\w()., ]+ => \{ ?)([A-Za-z_][\w.\[\]]*) = ([^=].*?)( ?\})\s*$")
ASSIGN_RE = re.compile(r"^(?P<ind>\s*)(?P<lhs>[A-Za-z_][\w.\[\]]*) = (?P<rhs>[^=].*?)\s*$")

def run_engine():
    p = subprocess.run([FROND, "run", "--", "check", "--std", "../std", PROBE],
                       cwd=CWD, capture_output=True, text=True, timeout=900,
                       encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")

def load(path):
    return io.open(path, encoding="utf-8").read().split("\n")

def save(path, lines):
    io.open(path, "w", encoding="utf-8", newline="").write("\n".join(lines))

def autofix(rounds):
    for r in range(rounds):
        out = run_engine()
        errs = re.findall(r"sema/([\w.]+\.frond):(\d+):(\d+): assignment type mismatch: cannot assign '([^']+)' to '([^']+)'", out)
        by_file = {}
        for fname, ln, col, t, tq in errs:
            if tq != t + "?":
                continue
            by_file.setdefault(fname, set()).add(int(ln))
        if not by_file:
            print("round", r, "no auto-fixable assignment errors")
            print(out[:1500])
            return
        total = 0
        for rel, lns in by_file.items():
            path = SEMA_DIR + "\\" + rel
            lines = load(path)
            for ln in sorted(lns, reverse=True):
                line = lines[ln - 1]
                if "if true {" in line:
                    print("SKIP", rel, ln, line.strip()[:70])
                    continue
                m2 = ARM_RE.match(line)
                if m2:
                    lines[ln - 1] = "%s%s = if true { %s } else { null }%s" % (m2.group(1), m2.group(2), m2.group(3), m2.group(4))
                    total += 1
                    continue
                m = ASSIGN_RE.match(line)
                if not m:
                    print("SKIP", rel, ln, line.strip()[:70])
                    continue
                tail = ""
                rhs = m.group("rhs")
                if line.rstrip().endswith("}"):
                    tail = " }"
                    rhs = rhs.rstrip()
                    if rhs.endswith("}"):
                        rhs = rhs[:-1].rstrip()
                lines[ln - 1] = "%s%s = if true { %s } else { null }%s" % (m.group("ind"), m.group("lhs"), rhs, tail)
                total += 1
            save(path, lines)
        print("round", r, "fixed", total)

if __name__ == "__main__":
    autofix(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
