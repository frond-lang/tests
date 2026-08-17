#!/usr/bin/env python3
"""Scan .frond stdlib for sync Throw-returning funs whose tail expression is
not Ok(...)/Err(...)/throw — the from_datetime_utc bug class.

Rules:
  - async fun with bare tail: LEGAL (engine auto-wraps Async<Throw<T,E>>, §4.3)
    -> reported as "async-bare (legal)" for inventory only
  - sync fun returning Throw with tail ending in '?': yields bare T -> BUG
  - sync fun returning Throw with bare value tail -> BUG
  - Ok(...) / Err(...) / throw / nested if|match arms -> judged by eye from dump
Skips @extern("C") raw bodies (#{ ... }#).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "Frond" / "src" / "stdlib"

sig_re = re.compile(r'^\s*(?:pub\s+)?(?:@\w+\s+)*(?:async\s+)?fun\s+\w+')

def strip_inline(comment_like):
    return comment_like

def scan(path: Path):
    findings = []
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    n = len(lines)
    in_raw = False
    while i < n:
        line = lines[i]
        # raw C block tracking: entered via #{ ... exited at }#
        if in_raw:
            if "}#" in line:
                in_raw = False
            i += 1
            continue
        if sig_re.match(line) and "fun " in line:
            # capture signature until '{'
            sig = line
            j = i
            while "{" not in sig and j + 1 < n and j - i < 6:
                j += 1
                sig += " " + lines[j].strip()
            if "{" not in sig:
                i += 1
                continue
            is_async = " async " in " " + sig
            is_throw = ": Throw<" in sig or ":Async<Throw" in sig.replace(" ", "")
            # fun name
            m = re.search(r'fun\s+(\w+)', sig)
            fname = m.group(1) if m else "?"
            if not is_throw:
                i = j + 1 if j > i else i + 1
                # skip body by depth
                i = skip_body(lines, i)
                continue
            # walk body from line j at depth 1
            body_start = j
            depth = 1
            k = j
            # position of '{' within line j
            opened = lines[j].count("{") - lines[j].count("}")
            depth = opened  # >=1
            last_lines = []  # (lineno, text) of body tail candidates
            k = j
            while k + 1 < n and depth > 0:
                k += 1
                t = lines[k]
                if "#{" in t:
                    # raw block inside body: skip to }#
                    while k + 1 < n and "}#" not in lines[k]:
                        k += 1
                    continue
                depth += t.count("{") - t.count("}")
            # body is lines (j+1 .. k-1), line k is the closing '}' (depth hit 0)
            # collect last non-empty lines before k
            tail = []
            b = k - 1
            while b > j and len(tail) < 3:
                t = lines[b].strip()
                if t:
                    tail.append((b + 1, t))
                b -= 1
            tail.reverse()
            findings.append((path, i + 1, fname, is_async, tail))
            i = k + 1
            continue
        if "#{" in line and "}#" not in line:
            in_raw = True
        i += 1
    return findings

def skip_body(lines, i):
    depth = 0
    started = False
    n = len(lines)
    while i < n:
        t = lines[i]
        if "#{" in t:
            while i < n and "}#" not in lines[i]:
                i += 1
            i += 1
            continue
        if "{" in t:
            started = True
        depth += t.count("{") - t.count("}")
        if started and depth <= 0:
            return i + 1
        i += 1
    return i

def classify(is_async, tail):
    if not tail:
        return "EMPTY-BODY?"
    last = tail[-1][1]
    if last.startswith("Ok(") or last.startswith("Ok ("):
        return "ok"
    if last.startswith("Err("):
        return "ok"
    if last.startswith("throw"):
        return "ok"
    if last.startswith("}#"):
        return "extern"
    # if/match block tails: need eyeball, mark bare
    if is_async:
        return "async-bare (legal)"
    return "SUSPECT-BARE"

def main():
    total_suspect = 0
    for f in sorted(ROOT.rglob("*.frond")):
        for (path, lineno, fname, is_async, tail) in scan(f):
            verdict = classify(is_async, tail)
            if verdict in ("ok", "extern"):
                continue
            total_suspect += 1 if verdict == "SUSPECT-BARE" else 0
            kind = "ASYNC" if is_async else "SYNC"
            print(f"{verdict}  {path.relative_to(ROOT)}:{lineno}  {kind} {fname}")
            for (ln, t) in tail:
                print(f"      L{ln}: {t[:110]}")
    print(f"\n--- sync suspects: {total_suspect}")

if __name__ == "__main__":
    main()
