#!/usr/bin/env python3
"""Static self-check for the eratohoЯeverse plugin system (guide section 6.3).

Checks: BOM + CRLF, quote pairing, block pairing, single-line colon SIF,
%..?..% conditionals, RETURNF outside #FUNCTIONS, bare [..] PRINT text,
GOTO label existence, and at-branch pairing.
"""
import glob
import re
import sys

BLOCK_PAIRS = [
    ("IF", "ENDIF"),
    ("FOR", "NEXT"),
    ("WHILE", "WEND"),
    ("DO", "LOOP"),
    ("SELECTCASE", "ENDSELECT"),
]
BRACKET_PAIRS = [("[IF_DEBUG]", "[ENDIF]"), ("[SKIPSTART]", "[SKIPEND]")]


def has_bare_colon(s):
    """True when a ':' appears at paren-depth 0 (a real single-line SIF).

    ':' inside parentheses is array-subscript syntax (e.g.
    SIF PLUGIN_ID:(LOCAL_I) == "") and is perfectly legal.
    """
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            tail = s[i + 1:].strip()
            # Subscript syntax, not a single-line SIF, when the ':' is directly
            # followed by a subscript: PLUGIN_ID:(LOCAL_I), ASSI:1,
            # TALENT:MASTER:男人, CFLAG:RESULT:LOCAL.
            if tail.startswith("(") or re.match(r"[A-Za-z0-9_\u3000-\u9fff]", tail):
                continue
            return True
    return False


def is_valid_bracket_expr(rest):
    """True when a leading [..] on a PRINT line is a legal numeric expression.

    Guide section 4.7: '[1] xxx' is fine because 1 parses as a numeric
    expression; '[demo] xxx' warns because 'demo' is bare text. {..} numeric
    expansions inside the brackets are also legal.
    """
    end = rest.find("]")
    if end < 0:
        return True
    inner = rest[1:end].strip()
    if inner == "":
        return True
    # strip {..} numeric expansions, then require pure numeric / operator text
    stripped = re.sub(r"\{[^}]*\}", "0", inner)
    return bool(re.fullmatch(r"[\d\s+\-*/%().]*", stripped))


def main(paths):
    problems = []
    files = []
    for p in paths:
        files.extend(sorted(glob.glob(p, recursive=True)))
    files = sorted(set(files))

    for f in files:
        raw = open(f, "rb").read()
        if not raw.startswith(b"\xef\xbb\xbf"):
            problems.append((f, "missing UTF-8 BOM"))
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            problems.append((f, "not valid UTF-8: %s" % e))
            continue
        if "\r\n" not in text and "\n" in text:
            problems.append((f, "no CRLF line endings"))
        lines = text.split("\r\n")

        stack = []
        labels = set()
        for ln in lines:
            s = ln.strip()
            if s.startswith("$"):
                labels.add(s[1:].strip())

        for n, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith(";") or not s:
                continue

            if s.count('"') % 2:
                problems.append((f, "L%d: odd double-quote count: %s" % (n, s[:70])))

            if re.match(r"^SIF\b", s) and has_bare_colon(s):
                problems.append((f, "L%d: single-line colon SIF: %s" % (n, s[:70])))

            for m in re.finditer(r"%[^%]*%", s):
                seg = m.group(0)
                if "?" not in seg:
                    continue
                # The legal display branch @ cond ? a # b @ may live inside a
                # %..% expansion; only a bare '?' operator is the trap.
                if seg.count("\\@") >= 2:
                    continue
                problems.append((f, "L%d: '?' inside %% expansion: %s" % (n, seg[:60])))

            if re.match(r"^RETURNF\b", s):
                problems.append((f, "L%d: RETURNF outside #FUNCTIONS" % n))

            m = re.match(r"^(PRINTL|PRINTFORML|PRINTFORM|PRINT)\s*(\[.*)", s)
            if m and not is_valid_bracket_expr(m.group(2)):
                problems.append((f, "L%d: bare [..] as PRINT text: %s" % (n, s[:70])))

            m = re.match(r"^GOTO\s+(\S+)", s)
            if m and m.group(1) not in labels:
                problems.append((f, "L%d: GOTO %s -> no matching $label in file" % (n, m.group(1))))

            for kw, cl in BLOCK_PAIRS:
                if re.match(r"^%s\b" % re.escape(kw), s, re.IGNORECASE):
                    stack.append((kw, n))
                elif re.match(r"^%s\b" % re.escape(cl), s, re.IGNORECASE):
                    if not stack:
                        problems.append((f, "L%d: unmatched %s" % (n, cl)))
                    else:
                        stack.pop()
            for op, cl in BRACKET_PAIRS:
                if s.startswith(op):
                    stack.append((op, n))
                elif s.startswith(cl):
                    if not stack:
                        problems.append((f, "L%d: unmatched %s" % (n, cl)))
                    else:
                        stack.pop()

        for kw, n in stack:
            problems.append((f, "unclosed %s opened at L%d" % (kw, n)))

        at = sum(ln.count("\\@") for ln in lines)
        if at % 2:
            problems.append((f, "odd number of \\@ branch markers (%d)" % at))

    print("checked %d file(s)" % len(files))
    for f in files:
        print("   ", f)
    print("%d problem(s)" % len(problems))
    for f, p in problems:
        print("  !", f, "->", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["ERB/PLUGIN/**/*.ERB", "ERB/PLUGIN/**/*.ERH"]))