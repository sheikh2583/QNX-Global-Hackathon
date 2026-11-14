"""Just enough C structure for safe, mechanical source transforms.

Not a C parser. Every helper works on a *masked* copy of the source in which comments and
string/char literals are blanked out (same length, newlines kept), so positions map 1:1 back to
the original text and nothing inside a comment or string can match. The remedies only rewrite
code they fully understand; anything ambiguous makes them back off to guidance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

IDENT = re.compile(r"\b[A-Za-z_]\w*\b")
KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum",
    "extern", "float", "for", "goto", "if", "inline", "int", "long", "register", "restrict", "return",
    "short", "signed", "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned", "void",
    "volatile", "while", "_Bool", "_Atomic", "bool", "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t", "size_t", "uintptr_t", "intptr_t", "NULL",
}
CONTROL_EXIT = re.compile(r"\b(return|break|continue|goto|longjmp|exit|_exit|abort)\b")


def mask(text: str) -> str:
    """Blank comments and string/char literals (keeping length and newlines)."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            for k in range(i + 1, min(j, n)):
                out[k] = " "
            i = j + 1
        elif c == "#" and (i == 0 or text[i - 1] == "\n" or text[:i].rsplit("\n", 1)[-1].strip() == ""):
            j = i  # preprocessor line (with continuations)
            while True:
                e = text.find("\n", j)
                if e < 0:
                    e = n
                    break
                if text[e - 1] != "\\":
                    break
                j = e + 1
            for k in range(i, e):
                if out[k] != "\n":
                    out[k] = " "
            i = e
        else:
            i += 1
    return "".join(out)


def match(m: str, i: int) -> int:
    """Index of the bracket closing the one at ``m[i]`` (``{``, ``(`` or ``[``)."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    open_c, close_c = m[i], pairs[m[i]]
    depth = 0
    for j in range(i, len(m)):
        if m[j] == open_c:
            depth += 1
        elif m[j] == close_c:
            depth -= 1
            if depth == 0:
                return j
    raise ValueError(f"unbalanced {open_c!r} at {i}")


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


@dataclass
class Function:
    name: str
    start: int  # start of the definition (return type)
    body_open: int  # index of '{'
    body_close: int  # index of matching '}'


def functions(m: str) -> list[Function]:
    out, i, depth = [], 0, 0
    while i < len(m):
        c = m[i]
        if c == "{" and depth == 0:
            head = m[:i].rstrip()
            if head.endswith(")"):
                p_open = _rmatch_paren(m, len(head) - 1)
                name_m = re.search(r"([A-Za-z_]\w*)\s*$", m[:p_open])
                if name_m and name_m.group(1) not in ("if", "while", "for", "switch"):
                    stmt_start = max(m.rfind(";", 0, name_m.start()), m.rfind("}", 0, name_m.start())) + 1
                    close = match(m, i)
                    out.append(Function(name_m.group(1), stmt_start, i, close))
                    i = close + 1
                    continue
            i = match(m, i) + 1
            continue
        i += 1
    return out


def _rmatch_paren(m: str, j: int) -> int:
    depth = 0
    for k in range(j, -1, -1):
        if m[k] == ")":
            depth += 1
        elif m[k] == "(":
            depth -= 1
            if depth == 0:
                return k
    raise ValueError("unbalanced ')'")


def top_level_decls(text: str, m: str | None = None) -> list[tuple[str, str, bool]]:
    """File-scope variable declarations: (name, declaration text, is_static). Functions excluded."""
    m = m if m is not None else mask(text)
    spans, i, start = [], 0, 0
    fn_spans = [(f.start, f.body_close) for f in functions(m)]
    while i < len(m):
        if any(a <= i <= b for a, b in fn_spans):
            i = next(b for a, b in fn_spans if a <= i <= b) + 1
            start = i
            continue
        c = m[i]
        if c == "{":
            i = match(m, i) + 1
            continue
        if c == ";":
            spans.append((start, i))
            start = i + 1
        i += 1
    out = []
    for a, b in spans:
        stmt = m[a:b]
        flat = re.sub(r"\{[^{}]*\}", " ", stmt)  # struct/union bodies and initializer lists
        while re.search(r"\{[^{}]*\}", flat):
            flat = re.sub(r"\{[^{}]*\}", " ", flat)
        if not flat.strip() or re.match(r"\s*typedef\b", flat):
            continue
        if re.search(r"[A-Za-z_]\w*\s*\([^()]*\)\s*$", flat.split("=")[0]):  # prototype
            continue
        static = bool(re.match(r"\s*static\b", flat))
        for part in _split_top(flat.split("=")[0] if "," not in flat else flat, ","):
            lhs = part.split("=")[0]
            lhs = re.sub(r"\[[^\]]*\]", " ", lhs)
            names = [x for x in IDENT.findall(lhs) if x not in KEYWORDS]
            if names:
                out.append((names[-1], text[a:b].strip(), static))
    return out


def _split_top(s: str, sep: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


@dataclass
class Stmt:
    start: int  # first code character (after leading whitespace/comments)
    end: int  # index just past the terminating ';' or '}'
    lead: int  # start of the line-region including leading comments/whitespace


def statements(m: str, a: int, b: int) -> list[Stmt]:
    """Top-level statements of the block body ``m[a:b]``."""
    out, i = [], a
    while i < b:
        lead = i
        while i < b and m[i].isspace():
            i += 1
        if i >= b:
            break
        start = i
        while i < b:
            c = m[i]
            if c in "([":
                i = match(m, i) + 1
                continue
            if c == "{":
                i = match(m, i) + 1
                rest = m[i:b].lstrip()
                if re.match(r"else\b", rest):
                    continue
                if re.match(r"while\b", rest) and re.match(r"do\b", m[start:]):
                    continue
                if m[start] == "{" or re.match(r"(if|for|while|switch|do|else)\b", m[start:]):
                    break
                continue  # initializer list inside a declaration: keep going to ';'
            if c == ";":
                i += 1
                if re.match(r"(if|else)\b", m[start:]) and re.match(r"\s*else\b", m[i:b]):
                    continue
                break
            i += 1
        out.append(Stmt(start, i, _line_start(m, lead, start)))
    return out


def _line_start(m: str, lead: int, start: int) -> int:
    """Statement text begins on the line after the previous statement, so comment lines above it
    and its indentation travel with it."""
    nl = m.find("\n", lead, start)
    return nl + 1 if nl >= 0 else lead


def idents(m: str, a: int, b: int) -> set[str]:
    return set(IDENT.findall(m[a:b])) - KEYWORDS


def calls(m: str, a: int, b: int) -> list[str]:
    return [x for x in re.findall(r"\b([A-Za-z_]\w*)\s*\(", m[a:b]) if x not in KEYWORDS
            and x not in ("if", "for", "while", "switch", "return", "sizeof")]


def tainted_locals(m: str, fn: Function, shared: set[str]) -> set[str]:
    """Local names that may alias shared data: assigned (anywhere in the function) from an
    expression that mentions a shared name or another tainted local."""
    body = m[fn.body_open + 1:fn.body_close]
    assigns = []
    for st in re.finditer(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?<![=!<>])=(?!=)([^;]*);", body):
        assigns.append((st.group(1), set(IDENT.findall(st.group(2)))))
    taint: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, rhs in assigns:
            if name not in taint and name not in shared and rhs & (shared | taint):
                taint.add(name)
                changed = True
    return taint
