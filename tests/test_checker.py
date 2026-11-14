import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "compiler"))

from lexer import ToyError
from ast_nodes import Name
from parser import parse
from parser import Parser
from checker import Checker, check
from toy_types import INT, BOOL, NULL, StructType, ArrayType


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


# ---------- step 3: types of expressions ----------
def type_of(text):
    """Parse an expression and return the type the checker gives it."""
    return Checker(None).check_expression(Parser(text).parse_expression())


def check_expression_error(text, expected):
    try:
        type_of(text)
    except ToyError as error:
        assert str(error) == expected, f"{text!r}: got {error}"
        return
    raise AssertionError(f"expected an error for {text!r}")


def test_literals_and_arithmetic():
    assert type_of("42") == INT
    assert type_of("true") == BOOL
    assert type_of("null") == NULL
    for text in ["1 + 2 * 3", "10 / 2 - 1", "10 % 3", "-5", "- -5"]:
        assert type_of(text) == INT, text


def test_comparisons_and_logic():
    for text in ["1 < 2", "1 >= 2", "1 == 1", "true != false", "null == null",
                 "!true", "true && false || true", "1 >= 2 == true"]:
        assert type_of(text) == BOOL, text


def test_type_is_stored_on_every_node():
    expression = Parser("1 + 2 * 3").parse_expression()
    Checker(None).check_expression(expression)
    assert expression.static_type == INT
    assert expression.right.static_type == INT
    assert expression.right.left.static_type == INT


def test_expression_errors():
    check_expression_error("1 + true",
                           "1:3: operator '+' requires two ints, not int and bool")
    check_expression_error("true % 2",
                           "1:6: operator '%' requires two ints, not bool and int")
    check_expression_error("!5", "1:1: operator '!' requires a bool, not int")
    check_expression_error("-true", "1:1: operator '-' requires an int, not bool")
    check_expression_error("1 == true",
                           "1:3: operator '==' requires compatible types, not int and bool")
    check_expression_error("null == 1",
                           "1:6: operator '==' requires compatible types, not null and int")
    check_expression_error("true < false",
                           "1:6: operator '<' requires two ints, not bool and bool")
    check_expression_error("1 && 2",
                           "1:3: operator '&&' requires two bools, not int and int")


# ---------- step 4: scopes and variables ----------
def place(line=1, column=1):
    return Name("_", line=line, column=column)


def test_variable_visible_in_inner_scope():
    checker = Checker(None)
    checker.enter_scope()
    checker.declare_variable("x", INT, place())
    checker.enter_scope()
    assert checker.lookup_variable("x", place()) == INT


def test_variable_disappears_with_its_scope():
    checker = Checker(None)
    checker.enter_scope()
    checker.enter_scope()
    checker.declare_variable("y", BOOL, place())
    checker.leave_scope()
    try:
        checker.lookup_variable("y", place(3, 2))
    except ToyError as error:
        assert str(error) == "3:2: undefined variable 'y'"
    else:
        raise AssertionError("y should be out of scope")


def test_no_masking():
    checker = Checker(None)
    checker.enter_scope()
    checker.declare_variable("x", INT, place())
    checker.enter_scope()
    try:
        checker.declare_variable("x", BOOL, place(2, 5))
    except ToyError as error:
        assert str(error) == "2:5: duplicate declaration of 'x'"
    else:
        raise AssertionError("masking must be refused")


def test_name_expression_uses_the_scope():
    checker = Checker(None)
    checker.enter_scope()
    checker.declare_variable("count", INT, place())
    expression = Parser("count + 1").parse_expression()
    assert checker.check_expression(expression) == INT
    try:
        checker.check_expression(Parser("other + 1").parse_expression())
    except ToyError as error:
        assert str(error) == "1:1: undefined variable 'other'"
    else:
        raise AssertionError("expected an error")


# ---------- step 5: remaining expressions ----------
def checker_with_variables():
    program = parse("struct Node { val: int; next: Node; } "
                    "fun push(head: Node, v: int): Node { } fun main(): int { }")
    checker = Checker(program)
    checker.collect_declarations()
    checker.enter_scope()
    for name, type_ in [("n", StructType("Node")), ("i", INT),
                        ("a", ArrayType(INT)), ("flag", BOOL)]:
        checker.declare_variable(name, type_, place())
    return checker


def test_remaining_expressions():
    checker = checker_with_variables()
    expected = {
        "n.val": INT, "n.next.next": StructType("Node"),
        "n.next == null": BOOL, "null == n": BOOL,
        "a[i + 1]": INT, "push(n, 1)": StructType("Node"), "push(null, i)": StructType("Node"),
        "new Node": StructType("Node"), "new int[10]": ArrayType(INT),
        "new Node[4]": ArrayType(StructType("Node")), "flag && i < 3": BOOL,
    }
    for text, expected_type in expected.items():
        assert checker.check_expression(Parser(text).parse_expression()) == expected_type, text


def test_remaining_expression_errors():
    cases = {
        "x": "1:1: undefined variable 'x'",
        "n.size": "1:2: unknown field 'size' in struct 'Node'",
        "i.val": "1:2: cannot access field 'val' of int",
        "a[true]": "1:3: array index must be an int, not bool",
        "i[0]": "1:2: cannot index int",
        "push(n)": "1:1: wrong number of arguments for 'push': expected 2, found 1",
        "push(1, 2)": "1:6: type mismatch: expected Node, found int",
        "nothing(1)": "1:1: undefined function 'nothing'",
        "new int[true]": "1:9: array size must be an int, not bool",
        "new Foo": "1:5: unknown type 'Foo'",
    }
    for text, message in cases.items():
        try:
            checker_with_variables().check_expression(Parser(text).parse_expression())
        except ToyError as error:
            assert str(error) == message, f"{text!r}: got {error}"
        else:
            raise AssertionError(f"expected an error for {text!r}")


# ---------- step 6: statements, functions, whole programs ----------
def in_main(body, before=""):
    return f"{before}fun main(): int {{ {body} return 0; }}"


def check_program_error(source_code, expected):
    try:
        check(parse(source_code))
    except ToyError as error:
        assert str(error) == expected, f"{source_code!r}: got {error}"
        return
    raise AssertionError(f"expected an error for {source_code!r}")


def test_example_files_pass_the_checker():
    for name in ["list.toy", "arrays.toy"]:
        with open(os.path.join(HERE, name), encoding="utf-8") as source_file:
            check(parse(source_file.read()))


def test_valid_programs():
    programs = [
        "fun f(a: bool): int { if (a) { return 1; } else { return 2; } } fun main(): int { return 0; }",
        "fun f(a: int): int { if (a < 0) { return 0; } else if (a == 0) { return 1; } else { return 2; } } "
        "fun main(): int { return 0; }",
        "struct N { } fun f(): N { return null; } fun main(): int { return 0; }",
        "fun f(): int { while (true) { } return 1; } fun main(): int { return 0; }",
        in_main("if (true) { var t: int; } if (true) { var t: bool; }"),
        "fun fact(n: int): int { if (n <= 1) { return 1; } return n * fact(n - 1); } "
        "fun main(): int { print(fact(5)); return 0; }",
        "fun a(n: int): bool { if (n == 0) { return true; } return b(n - 1); } "
        "fun b(n: int): bool { return a(n); } fun main(): int { return 0; }",
        "struct P { x: int; } fun main(): int { var ps: P[] = new P[3]; ps[0] = new P; "
        "ps[0].x = 7; print(ps[0].x); return 0; }",
        "fun f(x: int): int { return x; } " + in_main("f(1);"),
    ]
    for source_code in programs:
        check(parse(source_code))


def test_statement_errors():
    check_program_error(in_main("var x: int = true;"),
                        "1:32: type mismatch: expected int, found bool")
    check_program_error(in_main("y = 5;"), "1:19: undefined variable 'y'")
    check_program_error(in_main("var b: bool = true; b = 1;"),
                        "1:43: type mismatch: expected bool, found int")
    check_program_error(in_main("if (1) { }"), "1:23: condition must be a bool, not int")
    check_program_error(in_main("while (null) { }"), "1:26: condition must be a bool, not null")
    check_program_error("fun main(): int { return true; }",
                        "1:26: type mismatch: expected int, found bool")
    check_program_error("fun main(): int { return; }", "1:19: return requires a value")
    check_program_error(in_main("1 + 2;"), "1:19: only a call can be used as a statement")
    check_program_error(in_main("print(null);"),
                        "1:19: print requires an int or a bool, not null")
    check_program_error(in_main("var x: int; var x: int;"),
                        "1:31: duplicate declaration of 'x'")
    check_program_error(in_main("if (true) { var z: int; } z = 1;"),
                        "1:45: undefined variable 'z'")
    check_program_error(in_main("var x: int = x;"), "1:32: undefined variable 'x'")
    check_program_error(in_main("var n: Foo;"), "1:26: unknown type 'Foo'")
    check_program_error(
        in_main("var n: Node = new Node; n.val = true;", "struct Node { val: int; } "),
        "1:77: type mismatch: expected int, found bool")
    check_program_error(
        in_main("f(true);", "fun f(x: int): int { return x; } "),
        "1:54: type mismatch: expected int, found bool")


def test_function_errors():
    check_program_error(
        "fun f(): int { if (true) { return 1; } } fun main(): int { return 0; }",
        "1:1: missing return in function 'f'")
    check_program_error(
        "fun f(): int { while (true) { return 1; } } fun main(): int { return 0; }",
        "1:1: missing return in function 'f'")
    check_program_error(
        "fun f(a: int): int { var a: int; return 0; } fun main(): int { return 0; }",
        "1:22: duplicate declaration of 'a'")
    check_program_error(
        "fun f(a: int, a: int): int { return 0; } fun main(): int { return 0; }",
        "1:15: duplicate declaration of 'a'")


def test_checker_records_types_for_the_code_generator():
    with open(os.path.join(HERE, "list.toy"), encoding="utf-8") as source_file:
        program = check(parse(source_file.read()))
    push = next(f for f in program.functions if f.name == "push")
    assert [p.resolved_type for p in push.params] == [StructType("Node"), INT]
    new_node = push.body.statements[0]                  # var n: Node = new Node;
    assert new_node.resolved_type == StructType("Node")
    assert new_node.init.static_type == StructType("Node")
    assign_value = push.body.statements[1].value        # n.val = v;
    assert assign_value.static_type == INT


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
