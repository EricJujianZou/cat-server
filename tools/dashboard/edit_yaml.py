#!/usr/bin/env python3
"""Surgical edits to the YAML under config/, one key at a time.

The dashboard's settings form writes through here rather than round-tripping
the file with yaml.safe_dump. Every profile carries comments that explain
themselves, including the one saying why a Chinese voice and a Chinese
language line have to move together, and a dump would throw all of them away.

So this walks the lines, finds the key by its indentation, and replaces the
value in place. Anything it cannot find, it creates in the right block.
"""


def indent_of(s):
    return len(s) - len(s.lstrip(" "))


def is_blank(s):
    return not s.strip() or s.lstrip().startswith("#")


def block_end(lines, start, parent_indent):
    """The first line after `start` that is no longer inside its block."""
    for i in range(start + 1, len(lines)):
        if is_blank(lines[i]):
            continue
        if indent_of(lines[i]) <= parent_indent:
            return i
    return len(lines)


def find_key(lines, start, end, key, want_indent=None):
    for i in range(start, end):
        s = lines[i]
        if is_blank(s):
            continue
        if want_indent is not None and indent_of(s) != want_indent:
            continue
        if s.strip().split(":")[0].strip() == key:
            return i
    return -1


def child_indent(lines, parent, parent_indent, end):
    """How far the children of `parent` are indented, guessing two if empty."""
    for i in range(parent + 1, end):
        if not is_blank(lines[i]) and indent_of(lines[i]) > parent_indent:
            return indent_of(lines[i])
    return parent_indent + 2


def quote(value):
    """Only quote when leaving it bare would change the meaning.

    A real number or boolean goes in bare. A string that happens to look like
    one gets quotes, so a voice called `2` does not come back as an integer.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    s = str(value)
    if s == "" or s.strip() != s:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    looks_numeric = True
    try:
        float(s)
    except ValueError:
        looks_numeric = False
    bare_ok = (
        not looks_numeric
        and s[0] not in "#&*!|>%@`{}[],\"'-?:"
        and ":" not in s
        and "#" not in s
        and s.lower() not in ("true", "false", "null", "yes", "no", "on", "off", "~")
    )
    if bare_ok:
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_scalar(text, keypath, value):
    """Set `keypath` (a list of keys, outermost first) to a scalar.

    Returns the new text. Parent blocks that do not exist are appended at the
    end of the document rather than guessed at, because inserting a block into
    the middle of a commented file puts it under the wrong comment.
    """
    lines = text.split("\n")
    start, end, indent = 0, len(lines), 0

    for depth, key in enumerate(keypath):
        last = depth == len(keypath) - 1
        at = find_key(lines, start, end, key, indent)
        if at == -1:
            # Build whatever is left of the path as a fresh block at the end.
            tail = []
            for d, k in enumerate(keypath[depth:]):
                pad = " " * (indent + d * 2)
                if d == len(keypath[depth:]) - 1:
                    tail.append(f"{pad}{k}: {quote(value)}")
                else:
                    tail.append(f"{pad}{k}:")
            if indent == 0:
                while lines and not lines[-1].strip():
                    lines.pop()
                lines.extend([""] + tail + [""])
            else:
                lines[end:end] = tail
            return "\n".join(lines)
        if last:
            lines[at] = " " * indent + f"{key}: {quote(value)}"
            return "\n".join(lines)
        new_end = block_end(lines, at, indent)
        indent = child_indent(lines, at, indent, new_end)
        start, end = at + 1, new_end

    return "\n".join(lines)


def set_list(text, keypath, items):
    """Set `keypath` to a list, written inline when empty and as a block
    otherwise. Any existing list under that key is replaced whole."""
    lines = text.split("\n")
    start, end, indent = 0, len(lines), 0

    for depth, key in enumerate(keypath):
        last = depth == len(keypath) - 1
        at = find_key(lines, start, end, key, indent)
        if at == -1:
            tail = []
            for d, k in enumerate(keypath[depth:]):
                pad = " " * (indent + d * 2)
                if d == len(keypath[depth:]) - 1:
                    tail.extend(render_list(pad, k, items))
                else:
                    tail.append(f"{pad}{k}:")
            if indent == 0:
                while lines and not lines[-1].strip():
                    lines.pop()
                lines.extend([""] + tail + [""])
            else:
                lines[end:end] = tail
            return "\n".join(lines)
        if last:
            stop = block_end(lines, at, indent)
            # A block list is indented under the key, an inline one is not, so
            # block_end already covers both: it stops at the next key at this
            # level either way.
            lines[at:stop] = render_list(" " * indent, key, items)
            return "\n".join(lines)
        new_end = block_end(lines, at, indent)
        indent = child_indent(lines, at, indent, new_end)
        start, end = at + 1, new_end

    return "\n".join(lines)


def render_list(pad, key, items):
    if not items:
        return [f"{pad}{key}: []"]
    return [f"{pad}{key}:"] + [f"{pad}  - {quote(i)}" for i in items]


def read_scalar(text, keypath):
    """The raw value written at `keypath`, or None. Used to tell whether a
    value comes from the profile or is inherited from base.yaml."""
    lines = text.split("\n")
    start, end, indent = 0, len(lines), 0
    for depth, key in enumerate(keypath):
        at = find_key(lines, start, end, key, indent)
        if at == -1:
            return None
        if depth == len(keypath) - 1:
            return lines[at].split(":", 1)[1].strip().strip("'\"") or None
        new_end = block_end(lines, at, indent)
        indent = child_indent(lines, at, indent, new_end)
        start, end = at + 1, new_end
    return None
