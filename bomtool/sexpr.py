"""Tolerant S-expression parser for KiCad files (KiCad 6 through 10).

Parses into nested Python lists. Quoted strings become `Str` (a str subclass)
so they can be told apart from bare atoms, although callers rarely need that.
Unknown tokens are kept as-is, so new file versions do not break parsing.
"""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)
_ESC = re.compile(r'\\(.)', re.S)
_ESC_MAP = {"n": "\n", "t": "\t", "r": "\r"}


class Str(str):
    """A quoted string atom."""


def _unescape(s):
    if "\\" not in s:
        return s
    return _ESC.sub(lambda m: _ESC_MAP.get(m.group(1), m.group(1)), s)


def parse(text):
    """Parse text and return the first top-level expression."""
    stack = [[]]
    pos, n = 0, len(text)
    match = _TOKEN.match
    while pos < n:
        m = match(text, pos)
        if not m:
            # Trailing whitespace or garbage: stop quietly.
            break
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            if len(stack) > 1:
                done = stack.pop()
                stack[-1].append(done)
        elif m.group(3) is not None:
            stack[-1].append(Str(_unescape(m.group(3))))
        else:
            stack[-1].append(m.group(4))
    # Close anything left open (truncated file) instead of failing.
    while len(stack) > 1:
        done = stack.pop()
        stack[-1].append(done)
    top = stack[0]
    return top[0] if top else []


# ---- helpers for walking the tree -------------------------------------------

def head(node):
    return node[0] if isinstance(node, list) and node and isinstance(node[0], str) else None


def children(node, name=None):
    """Direct child lists, optionally filtered by head name."""
    if not isinstance(node, list):
        return []
    return [c for c in node[1:] if isinstance(c, list) and (name is None or head(c) == name)]


def child(node, name):
    for c in children(node, name):
        return c
    return None


def value(node, name, default=None, index=1):
    """Value of a direct `(name value ...)` child."""
    c = child(node, name)
    if c is None or len(c) <= index:
        return default
    v = c[index]
    return v if not isinstance(v, list) else default


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def flag(node, name, default=False):
    """KiCad booleans appear as `(name yes)`, `(name no)` or a bare `name` atom."""
    c = child(node, name)
    if c is not None:
        return len(c) < 2 or str(c[1]).lower() in ("yes", "true", "1")
    if isinstance(node, list) and name in [a for a in node[1:] if isinstance(a, str) and not isinstance(a, Str)]:
        return True
    return default


def properties(node):
    """Map of `(property "Name" "Value" ...)` children (KiCad 6+)."""
    out = {}
    for p in children(node, "property"):
        if len(p) >= 3 and not isinstance(p[1], list) and not isinstance(p[2], list):
            out[str(p[1])] = str(p[2])
    return out


def walk(node, name):
    """All descendants (depth first) with the given head."""
    if not isinstance(node, list):
        return
    for c in node[1:]:
        if isinstance(c, list):
            if head(c) == name:
                yield c
            yield from walk(c, name)
