"""Recursive-descent parser for Toy."""
from lexer import lex, ToyError
from ast_nodes import *

# precedence climbing table (higher binds tighter)
BINOPS = {
    "||": 1, "&&": 2,
    "==": 3, "!=": 3,
    "<": 4, "<=": 4, ">": 4, ">=": 4,
    "+": 5, "-": 5,
    "*": 6, "/": 6, "%": 6,
}


class Parser:
    def __init__(self, src):
        self.toks = lex(src)
        self.p = 0

    # ---- helpers ----
    @property
    def tok(self):
        return self.toks[self.p]

    def err(self, msg, t=None):
        t = t or self.tok
        raise ToyError(msg, t.line, t.col)

    def is_op(self, v):
        return self.tok.kind == "op" and self.tok.value == v

    def is_kw(self, v):
        return self.tok.kind == "kw" and self.tok.value == v

    def accept_op(self, v):
        if self.is_op(v):
            self.p += 1
            return True
        return False

    def expect_op(self, v):
        if not self.is_op(v):
            self.err(f"expected '{v}', found {self.tok.value!r}")
        t = self.tok
        self.p += 1
        return t

    def expect_kw(self, v):
        if not self.is_kw(v):
            self.err(f"expected '{v}', found {self.tok.value!r}")
        t = self.tok
        self.p += 1
        return t

    def expect_id(self):
        if self.tok.kind != "id":
            self.err(f"expected identifier, found {self.tok.value!r}")
        t = self.tok
        self.p += 1
        return t

    # ---- top level ----
    def parse_program(self):
        structs, funs = [], []
        while self.tok.kind != "eof":
            if self.is_kw("struct"):
                structs.append(self.parse_struct())
            elif self.is_kw("fun"):
                funs.append(self.parse_fun())
            else:
                self.err("expected 'struct' or 'fun'")
        return Program(structs, funs, line=1, col=1)

    def parse_struct(self):
        t = self.expect_kw("struct")
        name = self.expect_id().value
        self.expect_op("{")
        fields = []
        while not self.is_op("}"):
            ft = self.expect_id()
            self.expect_op(":")
            ty = self.parse_type()
            self.expect_op(";")
            fields.append(Field(ft.value, ty, line=ft.line, col=ft.col))
        self.expect_op("}")
        return StructDecl(name, fields, line=t.line, col=t.col)

    def parse_fun(self):
        t = self.expect_kw("fun")
        name = self.expect_id().value
        self.expect_op("(")
        params = []
        if not self.is_op(")"):
            while True:
                pt = self.expect_id()
                self.expect_op(":")
                params.append(Param(pt.value, self.parse_type(),
                                    line=pt.line, col=pt.col))
                if not self.accept_op(","):
                    break
        self.expect_op(")")
        self.expect_op(":")
        ret = self.parse_type()
        body = self.parse_block()
        return FunDecl(name, params, ret, body, line=t.line, col=t.col)

    # ---- types ----
    def parse_base_type(self):
        t = self.tok
        if t.kind == "kw" and t.value in ("int", "bool"):
            self.p += 1
            return TypeRef(t.value, 0, line=t.line, col=t.col)
        if t.kind == "id":
            self.p += 1
            return TypeRef(t.value, 0, line=t.line, col=t.col)
        self.err(f"expected a type, found {t.value!r}")

    def parse_type(self):
        ty = self.parse_base_type()
        while self.is_op("[") and self.toks[self.p + 1].value == "]":
            self.p += 2
            ty.dims += 1
        return ty

    # ---- statements ----
    def parse_block(self):
        t = self.expect_op("{")
        stmts = []
        while not self.is_op("}"):
            if self.tok.kind == "eof":
                self.err("unexpected end of file, missing '}'")
            stmts.append(self.parse_stmt())
        self.expect_op("}")
        return Block(stmts, line=t.line, col=t.col)

    def parse_stmt(self):
        t = self.tok
        if self.is_op("{"):
            return self.parse_block()
        if self.is_kw("var"):
            self.p += 1
            name = self.expect_id().value
            self.expect_op(":")
            ty = self.parse_type()
            init = None
            if self.accept_op("="):
                init = self.parse_expr()
            self.expect_op(";")
            return VarDecl(name, ty, init, line=t.line, col=t.col)
        if self.is_kw("if"):
            self.p += 1
            self.expect_op("(")
            cond = self.parse_expr()
            self.expect_op(")")
            then = self.parse_block()
            els = None
            if self.is_kw("else"):
                self.p += 1
                # allow `else if`
                els = (Block([self.parse_stmt()], line=t.line, col=t.col)
                       if self.is_kw("if") else self.parse_block())
            return If(cond, then, els, line=t.line, col=t.col)
        if self.is_kw("while"):
            self.p += 1
            self.expect_op("(")
            cond = self.parse_expr()
            self.expect_op(")")
            return While(cond, self.parse_block(), line=t.line, col=t.col)
        if self.is_kw("return"):
            self.p += 1
            val = None if self.is_op(";") else self.parse_expr()
            self.expect_op(";")
            return Return(val, line=t.line, col=t.col)
        if self.is_kw("print"):
            self.p += 1
            self.expect_op("(")
            val = self.parse_expr()
            self.expect_op(")")
            self.expect_op(";")
            return Print(val, line=t.line, col=t.col)
        # assignment or expression statement
        e = self.parse_expr()
        if self.accept_op("="):
            if not isinstance(e, (Name, FieldAccess, Index)):
                raise ToyError("invalid assignment target", e.line, e.col)
            val = self.parse_expr()
            self.expect_op(";")
            return Assign(e, val, line=t.line, col=t.col)
        self.expect_op(";")
        return ExprStmt(e, line=t.line, col=t.col)

    # ---- expressions ----
    def parse_expr(self, min_prec=1):
        left = self.parse_unary()
        while self.tok.kind == "op" and BINOPS.get(self.tok.value, 0) >= min_prec:
            op = self.tok
            prec = BINOPS[op.value]
            self.p += 1
            right = self.parse_expr(prec + 1)   # left-associative
            left = Binary(op.value, left, right, line=op.line, col=op.col)
        return left

    def parse_unary(self):
        t = self.tok
        if t.kind == "op" and t.value in ("-", "!"):
            self.p += 1
            return Unary(t.value, self.parse_unary(), line=t.line, col=t.col)
        return self.parse_postfix()

    def parse_postfix(self):
        e = self.parse_primary()
        while True:
            t = self.tok
            if self.accept_op("."):
                e = FieldAccess(e, self.expect_id().value, line=t.line, col=t.col)
            elif self.accept_op("["):
                idx = self.parse_expr()
                self.expect_op("]")
                e = Index(e, idx, line=t.line, col=t.col)
            else:
                return e

    def parse_primary(self):
        t = self.tok
        if t.kind == "int":
            self.p += 1
            return IntLit(t.value, line=t.line, col=t.col)
        if self.is_kw("true") or self.is_kw("false"):
            self.p += 1
            return BoolLit(t.value == "true", line=t.line, col=t.col)
        if self.is_kw("null"):
            self.p += 1
            return NullLit(line=t.line, col=t.col)
        if self.is_kw("new"):
            self.p += 1
            base = self.parse_base_type()
            if self.accept_op("["):
                size = self.parse_expr()
                self.expect_op("]")
                return NewArray(base, size, line=t.line, col=t.col)
            if base.base in ("int", "bool"):
                self.err("'new' needs a struct type or an array size", t)
            return NewObject(base, line=t.line, col=t.col)
        if t.kind == "id":
            self.p += 1
            if self.accept_op("("):
                args = []
                if not self.is_op(")"):
                    while True:
                        args.append(self.parse_expr())
                        if not self.accept_op(","):
                            break
                self.expect_op(")")
                return Call(t.value, args, line=t.line, col=t.col)
            return Name(t.value, line=t.line, col=t.col)
        if self.accept_op("("):
            e = self.parse_expr()
            self.expect_op(")")
            return e
        self.err(f"unexpected token {t.value!r}")


def parse(src: str) -> Program:
    return Parser(src).parse_program()
