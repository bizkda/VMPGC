"""Print the AST of a Toy file as a tree.

Usage:  python3 compiler/show_ast.py tests/list.toy
        python3 compiler/show_ast.py tests/list.toy --check   (also run the type checker)
        python3 compiler/show_ast.py tests/list.toy --ascii   (no special characters)
"""
import dataclasses
import sys

from lexer import ToyError
from ast_nodes import Node, TypeRef
from parser import parse
from checker import check

# (branch, last branch, vertical bar, blank) used to draw the tree
FANCY = ("├── ", "└── ", "│   ", "    ")
ASCII = ("|-- ", "`-- ", "|   ", "    ")
TYPE_FIELDS = ("static_type", "resolved_type")


def type_text(type_ref):
    return type_ref.base_type + "[]" * type_ref.dimension_count


def node_text(node, label):
    """One line describing a node: its class and its simple fields."""
    prefix = f"{label}: " if label else ""
    if isinstance(node, TypeRef):
        return f"{prefix}{type_text(node)}"
    simple = []
    for f in dataclasses.fields(node):
        value = getattr(node, f.name)
        if f.name in ("line", "column") or isinstance(value, (Node, list)):
            continue
        if f.name in TYPE_FIELDS:            # filled in by the type checker
            if value is not None:
                simple.append(f"{f.name}={value}")
            continue
        simple.append(f"{f.name}={value!r}")
    return f"{prefix}{type(node).__name__} {' '.join(simple)}".rstrip()


def child_entries(node):
    """(label, child) for every field that holds a node or a list of nodes."""
    if isinstance(node, TypeRef):
        return []
    entries = []
    for f in dataclasses.fields(node):
        child = getattr(node, f.name)
        if f.name not in ("line", "column") and isinstance(child, (Node, list)):
            entries.append((f.name, child))
    return entries


def print_tree(value, symbols, label="", prefix="", is_last=True, is_root=True):
    branch, last_branch, bar, blank = symbols

    if isinstance(value, list):
        text = f"{label} ({len(value)})"
        entries = [("", item) for item in value]
    else:
        text = node_text(value, label)
        entries = child_entries(value)

    if is_root:
        print(text)
        child_prefix = ""
    else:
        print(prefix + (last_branch if is_last else branch) + text)
        child_prefix = prefix + (blank if is_last else bar)

    for position, (child_label, child) in enumerate(entries):
        is_last_child = position == len(entries) - 1
        print_tree(child, symbols, child_label, child_prefix, is_last_child, False)


def main():
    options = [a for a in sys.argv[1:] if a.startswith("--")]
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    symbols = ASCII if "--ascii" in options else FANCY
    if len(arguments) != 1:
        print("usage: python3 compiler/show_ast.py <file.toy> [--check] [--ascii]")
        sys.exit(1)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    with open(arguments[0], encoding="utf-8") as source_file:
        source_code = source_file.read()
    try:
        program = parse(source_code)
        if "--check" in options:
            check(program)
    except ToyError as error:
        print(f"{arguments[0]}:{error}")
        sys.exit(1)
    print_tree(program, symbols)


if __name__ == "__main__":
    main()
