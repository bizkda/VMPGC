"""Print the AST of a Toy file as a readable tree.

Usage:  python3 compiler/show_ast.py tests/list.toy
"""
import dataclasses
import sys

from lexer import ToyError
from ast_nodes import Node, TypeRef
from parser import parse


def type_text(type_ref):
    return type_ref.base_type + "[]" * type_ref.dimension_count


def dump(value, indent=0, label=""):
    pad = "  " * indent
    prefix = f"{label}: " if label else ""

    if isinstance(value, TypeRef):
        print(f"{pad}{prefix}{type_text(value)}")
    elif isinstance(value, Node):
        fields = [f for f in dataclasses.fields(value)
                  if f.name not in ("line", "column")]
        simple = [f"{f.name}={getattr(value, f.name)!r}" for f in fields
                  if not isinstance(getattr(value, f.name), (Node, list))]
        print(f"{pad}{prefix}{type(value).__name__} {' '.join(simple)}".rstrip())
        for f in fields:
            child = getattr(value, f.name)
            if isinstance(child, (Node, list)):
                dump(child, indent + 1, f.name)
    elif isinstance(value, list):
        print(f"{pad}{prefix}({len(value)})")
        for item in value:
            dump(item, indent + 1)
    else:
        print(f"{pad}{prefix}{value!r}")


def main():
    if len(sys.argv) != 2:
        print("usage: python3 compiler/show_ast.py <file.toy>")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as source_file:
        source_code = source_file.read()
    try:
        program = parse(source_code)
    except ToyError as error:
        print(f"{sys.argv[1]}:{error}")
        sys.exit(1)
    dump(program)


if __name__ == "__main__":
    main()
