import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "compiler"))
from parser import parse
from lexer import ToyError
from ast_nodes import *

here = os.path.dirname(os.path.abspath(__file__))

def test_files():
    for f in glob.glob(os.path.join(here, "*.toy")):
        prog = parse(open(f).read())
        assert any(fn.name == "main" for fn in prog.funs), f

def test_precedence():
    p = parse("fun f(): int { return 1 + 2 * 3; }")
    e = p.funs[0].body.stmts[0].value
    assert e.op == "+" and e.right.op == "*"

def test_left_assoc():
    p = parse("fun f(): int { return 10 - 3 - 2; }")
    e = p.funs[0].body.stmts[0].value
    assert e.op == "-" and e.left.op == "-"

def test_array_and_field():
    p = parse("struct A { x: int; } fun f(a: A[]): int { a[0].x = 3; return 0; }")
    st = p.funs[0].body.stmts[0]
    assert isinstance(st, Assign) and isinstance(st.target, FieldAccess)
    assert isinstance(st.target.obj, Index)

def test_errors():
    for bad in ["fun f(: int {}", "fun f(): int { 1 = 2; }",
                "fun f(): int { var x: int = ; }", "fun f(): int { new int; }",
                "fun f(): int { @ }"]:
        try:
            parse(bad)
        except ToyError:
            continue
        raise AssertionError("expected error: " + bad)

if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
