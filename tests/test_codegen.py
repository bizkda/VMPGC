import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))   # the project root

from compiler.frontend.lexer import ToyError
from compiler.frontend.parser import parse
from compiler.frontend.semantique import Checker
from compiler.backend.codegen import TypeTable, FunctionGenerator
from compiler.backend.bytecode import STRUCT, ARRAY_OF_VALUES, ARRAY_OF_REFERENCES


def compile_functions(source_code):
    """Parse, check and generate code. Returns ({name: FunctionCode}, TypeTable)."""
    program = parse(source_code)
    checker = Checker(program)
    checker.check_program()
    table = TypeTable(program, checker.struct_fields)
    indexes = {f.name: i for i, f in enumerate(program.functions)}
    generator = FunctionGenerator(checker, table, indexes)
    return {f.name: generator.generate(f) for f in program.functions}, table


def code_of(source_code, name="main"):
    codes, _ = compile_functions(source_code)
    return [(i.opcode, i.operand) for i in codes[name].instructions]


def maps_of(source_code, name="main"):
    codes, _ = compile_functions(source_code)
    return [(m.pc, m.depth, m.locals_mask, m.stack_mask) for m in codes[name].stack_maps]


def in_main(body, before=""):
    return f"{before}fun main(): int {{ {body} return 0; }}"


# ---------- expressions ----------
def test_arithmetic_order():
    assert code_of("fun main(): int { return 1 + 2 * 3; }") == [
        ("PUSH_INT", 1), ("PUSH_INT", 2), ("PUSH_INT", 3), ("MUL", 0), ("ADD", 0), ("RET", 0)]


def test_unary_and_comparison():
    assert code_of("fun main(): int { var b: bool = !(1 < 2); return 0; }") == [
        ("PUSH_INT", 1), ("PUSH_INT", 2), ("LT", 0), ("NOT", 0), ("STORE_LOCAL", 0),
        ("PUSH_INT", 0), ("RET", 0)]
    assert code_of("fun main(): int { return -5; }") == [
        ("PUSH_INT", 5), ("NEG", 0), ("RET", 0)]


def test_short_circuit_and():
    source = "fun f(a: bool, b: bool): bool { return a && b; } fun main(): int { return 0; }"
    assert code_of(source, "f") == [
        ("LOAD_LOCAL", 0), ("JZ", 4), ("LOAD_LOCAL", 1), ("JMP", 5),
        ("PUSH_INT", 0), ("RET", 0)]


def test_short_circuit_or():
    source = "fun f(a: bool, b: bool): bool { return a || b; } fun main(): int { return 0; }"
    assert code_of(source, "f") == [
        ("LOAD_LOCAL", 0), ("JZ", 4), ("PUSH_INT", 1), ("JMP", 5),
        ("LOAD_LOCAL", 1), ("RET", 0)]


# ---------- statements ----------
def test_while_loop():
    source = "fun main(): int { var i: int = 0; while (i < 3) { i = i + 1; } return i; }"
    assert code_of(source) == [
        ("PUSH_INT", 0), ("STORE_LOCAL", 0),
        ("LOAD_LOCAL", 0), ("PUSH_INT", 3), ("LT", 0), ("JZ", 11),
        ("LOAD_LOCAL", 0), ("PUSH_INT", 1), ("ADD", 0), ("STORE_LOCAL", 0), ("JMP", 2),
        ("LOAD_LOCAL", 0), ("RET", 0)]


def test_if_else_when_both_branches_return():
    source = ("fun f(a: bool): int { if (a) { return 1; } else { return 2; } } "
              "fun main(): int { return 0; }")
    assert code_of(source, "f") == [
        ("LOAD_LOCAL", 0), ("JZ", 4), ("PUSH_INT", 1), ("RET", 0),
        ("PUSH_INT", 2), ("RET", 0)]


def test_if_else_that_falls_through():
    source = ("fun f(a: bool): int { var x: int = 0; if (a) { x = 1; } else { x = 2; } return x; } "
              "fun main(): int { return 0; }")
    assert code_of(source, "f") == [
        ("PUSH_INT", 0), ("STORE_LOCAL", 1),
        ("LOAD_LOCAL", 0), ("JZ", 7),
        ("PUSH_INT", 1), ("STORE_LOCAL", 1), ("JMP", 9),
        ("PUSH_INT", 2), ("STORE_LOCAL", 1),
        ("LOAD_LOCAL", 1), ("RET", 0)]


def test_if_without_else():
    source = ("fun f(a: bool): int { var x: int = 0; if (a) { x = 1; } return x; } "
              "fun main(): int { return 0; }")
    assert code_of(source, "f") == [
        ("PUSH_INT", 0), ("STORE_LOCAL", 1),
        ("LOAD_LOCAL", 0), ("JZ", 6),
        ("PUSH_INT", 1), ("STORE_LOCAL", 1),
        ("LOAD_LOCAL", 1), ("RET", 0)]


def test_variables_without_value_get_their_default():
    source = in_main("var x: int; var b: bool; var n: Node;", "struct Node { } ")
    assert code_of(source) == [
        ("PUSH_INT", 0), ("STORE_LOCAL", 0), ("PUSH_INT", 0), ("STORE_LOCAL", 1),
        ("PUSH_NULL", 0), ("STORE_LOCAL", 2), ("PUSH_INT", 0), ("RET", 0)]


def test_each_declaration_has_its_own_slot():
    source = in_main("if (true) { var t: int; } if (true) { var t: bool; }")
    codes, _ = compile_functions(source)
    assert codes["main"].local_count == 2


def test_print_kinds():
    assert code_of(in_main("print(1); print(true);")) == [
        ("PUSH_INT", 1), ("PRINT_INT", 0), ("PUSH_INT", 1), ("PRINT_BOOL", 0),
        ("PUSH_INT", 0), ("RET", 0)]


def test_call_as_statement_drops_the_result():
    source = "fun f(x: int): int { return x; } " + in_main("f(1);")
    assert code_of(source) == [
        ("PUSH_INT", 1), ("CALL", 0), ("POP", 0), ("PUSH_INT", 0), ("RET", 0)]


# ---------- objects and arrays ----------
def test_field_access_and_assignment():
    source = ("struct Node { val: int; next: Node; } "
              "fun f(n: Node): Node { n.val = 5; return n.next; } fun main(): int { return 0; }")
    assert code_of(source, "f") == [
        ("LOAD_LOCAL", 0), ("PUSH_INT", 5), ("PUTFIELD", 0),
        ("LOAD_LOCAL", 0), ("GETFIELD", 1), ("RET", 0)]


def test_array_store_and_load():
    source = in_main("var a: int[] = new int[2]; a[1] = 7; print(a[1]);")
    assert code_of(source) == [
        ("PUSH_INT", 2), ("NEW_ARRAY", 1), ("STORE_LOCAL", 0),
        ("LOAD_LOCAL", 0), ("PUSH_INT", 1), ("PUSH_INT", 7), ("ASTORE", 0),
        ("LOAD_LOCAL", 0), ("PUSH_INT", 1), ("ALOAD", 0), ("PRINT_INT", 0),
        ("PUSH_INT", 0), ("RET", 0)]


def test_push_matches_the_specifications():
    with open(os.path.join(HERE, "list.toy"), encoding="utf-8") as source_file:
        source = source_file.read()
    assert code_of(source, "push") == [
        ("NEW", 1), ("STORE_LOCAL", 2), ("LOAD_LOCAL", 2), ("LOAD_LOCAL", 1),
        ("PUTFIELD", 0), ("LOAD_LOCAL", 2), ("LOAD_LOCAL", 0), ("PUTFIELD", 1),
        ("LOAD_LOCAL", 2), ("RET", 0)]
    assert maps_of(source, "push") == [(0, 0, 0b101, 0)]      # locals 101, empty stack


# ---------- stack maps ----------
def test_stack_map_sees_references_waiting_on_the_stack():
    source = ("struct Node { } fun g(a: Node, b: Node): int { return 0; } "
              "fun main(): int { var r: int = g(new Node, new Node); return r; }")
    assert code_of(source) == [
        ("NEW", 1), ("NEW", 1), ("CALL", 0), ("STORE_LOCAL", 0), ("LOAD_LOCAL", 0), ("RET", 0)]
    assert maps_of(source) == [
        (0, 0, 0, 0b0),     # first NEW: nothing waiting
        (1, 1, 0, 0b1),     # second NEW: the first object is waiting (a reference)
        (2, 0, 0, 0b0)]     # CALL: the two arguments are already popped


def test_stack_map_marks_ints_and_references_apart():
    source = in_main("var ps: P[] = new P[3]; ps[0] = new P;", "struct P { x: int; } ")
    assert maps_of(source) == [
        (1, 0, 0b1, 0b00),  # NEW_ARRAY: the size is already popped
        (5, 2, 0b1, 0b01)]  # NEW inside ps[0] = new P: stack is [ps (ref), 0 (int)]


def test_getfield_result_kind_is_tracked():
    base = ("struct Node { val: int; next: Node; } "
            "fun g(a: Node, b: Node): int { return 0; } "
            "fun h(a: int, b: Node): int { return 0; } ")
    with_reference = base + "fun f(n: Node): int { return g(n.next, new Node); } " \
                            "fun main(): int { return 0; }"
    with_int = base + "fun f(n: Node): int { return h(n.val, new Node); } " \
                      "fun main(): int { return 0; }"
    assert maps_of(with_reference, "f")[0] == (2, 1, 0b1, 0b1)   # n.next is a reference
    assert maps_of(with_int, "f")[0] == (2, 1, 0b1, 0b0)         # n.val is an int


def test_short_circuit_keeps_the_stack_model_consistent():
    # the JZ of && pops `a`, so the NEW inside the right operand sees an empty stack
    source = ("struct N { } fun f(a: bool, n: N): bool { return a && (new N == null); } "
              "fun main(): int { return 0; }")
    assert maps_of(source, "f") == [(2, 0, 0b10, 0)]

    # with a reference waiting below, both paths of && must agree on the stack
    source = ("struct N { } fun g(x: N, y: bool): bool { return y; } "
              "fun f(a: bool): bool { return g(new N, a && (new N == null)); } "
              "fun main(): int { return 0; }")
    assert maps_of(source, "f") == [
        (0, 0, 0, 0b0),     # first NEW
        (3, 1, 0, 0b1),     # NEW in the right operand: the first object is still waiting
        (8, 0, 0, 0b0)]     # CALL after the && has produced its bool


# ---------- type table ----------
def test_type_ids_and_descriptors():
    with open(os.path.join(HERE, "arrays.toy"), encoding="utf-8") as source_file:
        _, table = compile_functions(source_file.read())
    entries = [(e.type_id, e.kind, e.name, e.field_count, e.pointer_mask) for e in table.entries]
    assert entries == [
        (1, STRUCT, "Tree", 3, 0b011),            # left and right are references, key is not
        (2, ARRAY_OF_VALUES, "int[]", 0, 0),
        (3, ARRAY_OF_REFERENCES, "Tree[]", 0, 0)]


def test_an_array_type_gets_one_id():
    source = in_main("var a: int[] = new int[1]; var b: int[] = new int[2]; "
                     "var c: bool[] = new bool[1];")
    _, table = compile_functions(source)
    assert [e.name for e in table.entries] == ["int[]", "bool[]"]


# ---------- limits ----------
def test_limits():
    def error_of(source):
        try:
            compile_functions(source)
        except ToyError as error:
            return str(error)
        raise AssertionError("expected an error")

    assert error_of("fun main(): int { return 2147483648; }") == \
        "1:26: integer literal too large (maximum 2147483647)"
    compile_functions("fun main(): int { return 2147483647; }")

    many_locals = in_main("".join(f"var v{i}: int; " for i in range(65)))
    assert error_of(many_locals).endswith("function has more than 64 local variables")

    many_fields = ("struct S { " + "".join(f"f{i}: int; " for i in range(65)) + "} "
                   "fun main(): int { return 0; }")
    assert error_of(many_fields) == "1:1: struct 'S' has more than 64 fields"

    deep = "fun main(): int { return " + "1 + (" * 65 + "new int[1][0]" + ")" * 65 + "; }"
    assert "expression too complex" in error_of(deep)


# ---------- the example programs ----------
def test_example_files_generate_code():
    for name in ["list.toy", "arrays.toy"]:
        with open(os.path.join(HERE, name), encoding="utf-8") as source_file:
            codes, _ = compile_functions(source_file.read())
        for code in codes.values():
            assert code.instructions[-1].opcode == "RET", (name, code.name)


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
