import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "compiler"))

from lexer import ToyError
from ast_nodes import *
from parser import parse, Parser


def body_of(source_code):
    """Statements of the single function in `source_code`."""
    return parse(source_code).functions[0].body.statements


def expression_of(text):
    return Parser(text).parse_expression()


# ---------- whole programs ----------
def test_example_files():
    expected = {"list.toy": (1, 2), "arrays.toy": (1, 2)}
    for name, (struct_count, function_count) in expected.items():
        with open(os.path.join(HERE, name), encoding="utf-8") as source_file:
            program = parse(source_file.read())
        assert len(program.structs) == struct_count, name
        assert len(program.functions) == function_count, name
        assert any(f.name == "main" for f in program.functions), name


def test_empty_program():
    program = parse("")
    assert program.structs == [] and program.functions == []


# ---------- expressions ----------
def test_precedence():
    e = expression_of("1 + 2 * 3")
    assert e.operator == "+" and e.right.operator == "*"


def test_left_associativity():
    e = expression_of("10 - 3 - 2")
    assert e.operator == "-" and e.left.operator == "-"
    assert isinstance(e.right, IntLiteral) and e.right.value == 2


def test_parentheses():
    e = expression_of("(1 + 2) * 3")
    assert e.operator == "*" and e.left.operator == "+"


def test_logical_precedence():
    e = expression_of("a || b && c")
    assert e.operator == "||" and e.right.operator == "&&"


def test_comparison_binds_tighter_than_logic():
    e = expression_of("a < b && c == d")
    assert e.operator == "&&"
    assert e.left.operator == "<" and e.right.operator == "=="


def test_unary():
    e = expression_of("-a * b")
    assert e.operator == "*" and isinstance(e.left, Unary) and e.left.operator == "-"
    e = expression_of("!a && b")
    assert e.operator == "&&" and isinstance(e.left, Unary) and e.left.operator == "!"
    e = expression_of("- -5")
    assert isinstance(e, Unary) and isinstance(e.operand, Unary)


def test_literals():
    assert isinstance(expression_of("true"), BoolLiteral)
    assert expression_of("false").value is False
    assert isinstance(expression_of("null"), NullLiteral)
    assert expression_of("42").value == 42


def test_calls():
    e = expression_of("f()")
    assert isinstance(e, Call) and e.function_name == "f" and e.arguments == []
    e = expression_of("push(head, 1 + 2)")
    assert len(e.arguments) == 2 and e.arguments[1].operator == "+"


def test_postfix_chain():
    e = expression_of("a[0].next.val")
    assert isinstance(e, FieldAccess) and e.field_name == "val"
    assert isinstance(e.target_object, FieldAccess)
    assert isinstance(e.target_object.target_object, Index)


def test_new_expressions():
    e = expression_of("new Node")
    assert isinstance(e, NewObject) and e.type.base_type == "Node"
    e = expression_of("new int[n + 1]")
    assert isinstance(e, NewArray) and e.element_type.base_type == "int"
    assert e.size.operator == "+"
    e = expression_of("new Node[4]")
    assert isinstance(e, NewArray) and e.element_type.base_type == "Node"


# ---------- statements ----------
def test_var_declaration():
    with_init, without_init = body_of("fun f(): int { var x: int = 5; var y: Node[]; }")
    assert isinstance(with_init, VarDecl) and with_init.init.value == 5
    assert without_init.init is None and without_init.type.dimension_count == 1


def test_assignment_targets():
    name, field, element = body_of("fun f(): int { x = 1; a.b = 2; a[0].x = 3; }")
    assert isinstance(name.target, Name)
    assert isinstance(field.target, FieldAccess)
    assert isinstance(element.target, FieldAccess)
    assert isinstance(element.target.target_object, Index)


def test_expression_statement():
    (statement,) = body_of("fun f(): int { push(a, 1); }")
    assert isinstance(statement, ExpressionStatement)
    assert isinstance(statement.expression, Call)


def test_if_else_if_else():
    (statement,) = body_of(
        "fun f(): int { if (a) { x = 1; } else if (b) { x = 2; } else { x = 3; } }")
    assert isinstance(statement, IfStatement)
    nested = statement.else_block.statements[0]
    assert isinstance(nested, IfStatement)
    assert nested.else_block is not None


def test_if_without_else():
    (statement,) = body_of("fun f(): int { if (a) { } }")
    assert statement.else_block is None


def test_while_return_print():
    loop, ret, show = body_of(
        "fun f(): int { while (i < 3) { i = i + 1; } return; print(i); }")
    assert isinstance(loop, WhileStatement) and len(loop.body.statements) == 1
    assert isinstance(ret, ReturnStatement) and ret.value is None
    assert isinstance(show, PrintStatement)


def test_nested_block():
    (statement,) = body_of("fun f(): int { { var x: int; } }")
    assert isinstance(statement, Block)


# ---------- declarations ----------
def test_struct_and_function():
    program = parse("struct A { x: int; next: A; } fun f(a: A[], n: int): bool { }")
    assert [f.name for f in program.structs[0].fields] == ["x", "next"]
    function = program.functions[0]
    assert [p.name for p in function.params] == ["a", "n"]
    assert function.params[0].type.dimension_count == 1
    assert function.return_type.base_type == "bool"


# ---------- errors (message and position) ----------
def check_error(source_code, expected):
    try:
        parse(source_code)
    except ToyError as error:
        assert str(error) == expected, f"{source_code!r}: got {error}"
        return
    raise AssertionError(f"expected an error for {source_code!r}")


def test_errors():
    check_error("fun f(: int { }", "1:7: expected an identifier, found ':'")
    check_error("fun f(): int", "1:13: expected '{', found end of file")
    check_error("fun f(): int {", "1:15: expected '}', found end of file")
    check_error("fun f(): int { 1 = 2; }", "1:16: invalid assignment target")
    check_error("fun f(): int { var x: int = ; }",
                "1:29: expected an expression, found ';'")
    check_error("fun f(): int { new int; }",
                "1:16: 'new' needs a struct type or an array size")
    check_error("fun f(): int { x = 1 }", "1:22: expected ';', found '}'")
    check_error("fun f(): int { if a { } }", "1:19: expected '(', found 'a'")
    check_error("fun f(): int { f(1, ); }", "1:21: expected an expression, found ')'")
    check_error("fun f(): int { a[1; }", "1:19: expected ']', found ';'")
    check_error("var x: int;", "1:1: expected 'struct' or 'fun', found 'var'")
    check_error("fun f(): int { @ }", "1:16: unexpected character '@'")


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
