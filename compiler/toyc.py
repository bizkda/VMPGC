#!/usr/bin/env python3
"""The Toy compiler.

Usage:  python3 compiler/toyc.py <source.toy> [-o <output.tbc>] [--dump]

  -o FILE   where to write the bytecode (default: the source name with .tbc)
  --dump    also print the bytecode as readable text

Exit code: 0 if the compilation succeeds, 1 otherwise (and no .tbc file is written).
"""
import os
import sys

if __package__ in (None, ""):
    # run as a plain script: make `import compiler...` work by adding the project root
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from compiler.frontend.lexer import ToyError
from compiler.backend.program import compile_source
from compiler.backend.tbc import write_tbc
from compiler.backend.disassembler import format_program

USAGE = "usage: python3 compiler/toyc.py <source.toy> [-o <output.tbc>] [--dump]"


def main(arguments):
    source_path, output_path, dump = None, None, False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--dump":
            dump = True
        elif argument == "-o":
            index += 1
            if index >= len(arguments):
                print(USAGE, file=sys.stderr)
                return 1
            output_path = arguments[index]
        elif argument.startswith("-") or source_path is not None:
            print(USAGE, file=sys.stderr)
            return 1
        else:
            source_path = argument
        index += 1
    if source_path is None:
        print(USAGE, file=sys.stderr)
        return 1
    if output_path is None:
        output_path = os.path.splitext(source_path)[0] + ".tbc"

    try:
        with open(source_path, encoding="utf-8") as source_file:
            source_code = source_file.read()
    except OSError as error:
        print(f"toyc: cannot read {source_path}: {error.strerror}", file=sys.stderr)
        return 1

    try:
        program_code = compile_source(source_code)
    except ToyError as error:
        print(f"{source_path}:{error}", file=sys.stderr)
        return 1

    if dump:
        print(format_program(program_code), end="")
    write_tbc(program_code, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
