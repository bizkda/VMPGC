import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))   # the project root
from compiler.frontend.lexer import lex, ToyError


def kinds_and_values(source_code):
    return [(token.kind, token.value) for token in lex(source_code)]


def test_variable_declaration():
    assert kinds_and_values("var x: int = 5;") == [
        ("keyword", "var"), ("identifier", "x"), ("operator", ":"),
        ("keyword", "int"), ("operator", "="), ("integer", 5),
        ("operator", ";"), ("eof", None),
    ]


def test_two_char_operator_is_one_token():
    assert kinds_and_values("a == b")[1] == ("operator", "==")


def test_comment_is_ignored_and_lines_are_counted():
    tokens = lex("x // comment\ny")
    assert [t.value for t in tokens[:-1]] == ["x", "y"]
    assert tokens[1].line == 2 and tokens[1].column == 1


def test_unknown_character():
    try:
        lex("a @ b")
    except ToyError as error:
        assert str(error) == "1:3: unexpected character '@'"
    else:
        raise AssertionError("expected a ToyError")


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
