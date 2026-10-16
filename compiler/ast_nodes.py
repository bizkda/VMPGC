"""AST node definitions for Toy.

Types in the AST are TypeRef; the type checker (M2) resolves them.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Node:
    line: int = field(default=0, kw_only=True)
    col: int = field(default=0, kw_only=True)


# ---- types ----
@dataclass
class TypeRef(Node):
    base: str            # 'int', 'bool', or a struct name
    dims: int = 0        # number of [] suffixes

    def __str__(self):
        return self.base + "[]" * self.dims


# ---- top level ----
@dataclass
class Field(Node):
    name: str
    type: TypeRef


@dataclass
class StructDecl(Node):
    name: str
    fields: List[Field]


@dataclass
class Param(Node):
    name: str
    type: TypeRef


@dataclass
class FunDecl(Node):
    name: str
    params: List[Param]
    ret: TypeRef
    body: "Block"


@dataclass
class Program(Node):
    structs: List[StructDecl]
    funs: List[FunDecl]


# ---- statements ----
@dataclass
class Block(Node):
    stmts: List[Node]


@dataclass
class VarDecl(Node):
    name: str
    type: TypeRef
    init: Optional[Node]


@dataclass
class Assign(Node):
    target: Node         # Name | FieldAccess | Index
    value: Node


@dataclass
class If(Node):
    cond: Node
    then: Block
    els: Optional[Block]


@dataclass
class While(Node):
    cond: Node
    body: Block


@dataclass
class Return(Node):
    value: Optional[Node]


@dataclass
class Print(Node):
    value: Node


@dataclass
class ExprStmt(Node):
    expr: Node


# ---- expressions ----
@dataclass
class IntLit(Node):
    value: int


@dataclass
class BoolLit(Node):
    value: bool


@dataclass
class NullLit(Node):
    pass


@dataclass
class Name(Node):
    name: str


@dataclass
class Unary(Node):
    op: str
    operand: Node


@dataclass
class Binary(Node):
    op: str
    left: Node
    right: Node


@dataclass
class Call(Node):
    name: str
    args: List[Node]


@dataclass
class FieldAccess(Node):
    obj: Node
    name: str


@dataclass
class Index(Node):
    arr: Node
    index: Node


@dataclass
class NewObject(Node):
    type: TypeRef        # struct type


@dataclass
class NewArray(Node):
    elem: TypeRef        # element type
    size: Node
