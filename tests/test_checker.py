import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "compiler"))

from lexer import ToyError
from parser import parse
from checker import Checker
from toy_types import INT, BOOL, StructType, ArrayType


def collect(source_code):
    program = parse(source_code)
    checker = Checker(program)
    checker.collect_declarations()
    return program, checker


def check_error(source_code, expected):
    try:
        collect(source_code)
    except ToyError as error:
        assert str(error) == expected, f"{source_code!r}: got {error}"
        return
    raise AssertionError(f"expected an error for {source_code!r}")


def test_struct_fields():
    _, checker = collect("struct Node { val: int; next: Node; items: int[]; } "
                         "fun main(): int { }")
    fields = checker.struct_fields["Node"]
    assert fields["val"] == INT
    assert fields["next"] == StructType("Node")
    assert fields["items"] == ArrayType(INT)


def test_structs_that_refer_to_each_other():
    _, checker = collect("struct A { b: B; } struct B { a: A[]; } fun main(): int { }")
    assert checker.struct_fields["A"]["b"] == StructType("B")
    assert checker.struct_fields["B"]["a"] == ArrayType(StructType("A"))


def test_function_signatures():
    _, checker = collect("fun main(): int { } "
                         "fun later(n: Node, ok: bool): bool[] { } "
                         "struct Node { }")
    signature = checker.functions["later"]
    assert signature.parameter_types == [StructType("Node"), BOOL]
    assert signature.return_type == ArrayType(BOOL)
    assert checker.functions["main"].return_type == INT


def test_ast_is_not_modified():
    program, _ = collect("struct A { } struct B { } fun main(): int { }")
    assert len(program.structs) == 2 and len(program.functions) == 1


def test_errors():
    check_error("struct A { } struct A { } fun main(): int { }",
                "1:14: duplicate struct 'A'")
    check_error("struct A { x: int; x: bool; } fun main(): int { }",
                "1:20: duplicate field 'x' in struct 'A'")
    check_error("struct A { x: B; } fun main(): int { }",
                "1:15: unknown type 'B'")
    check_error("fun f(a: int[][]): int { } fun main(): int { }",
                "1:10: arrays of arrays are not supported")
    check_error("fun f(): int { } fun f(): int { } fun main(): int { }",
                "1:18: duplicate function 'f'")
    check_error("fun f(): int { }", "1:1: missing function 'main'")
    check_error("fun main(a: int): int { }",
                "1:1: 'main' must have no parameters and return int")
    check_error("fun main(): bool { }",
                "1:1: 'main' must have no parameters and return int")


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")