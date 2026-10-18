from dataclasses import dataclass, field
from typing import List, Optional


# ---------- bases ----------
@dataclass
class Node:
    
    line: int = field(default=0, kw_only=True)
    column: int = field(default=0, kw_only=True)


@dataclass
class Statement(Node):
    pass


@dataclass
class Expression(Node):
    pass



@dataclass
class TypeRef(Node):
    # TypeRef("int")                      -> int
    # TypeRef("int", dimension_count=1)   -> int[]
    # TypeRef("Node", dimension_count=1)  -> Node[]
    base_type: str
    dimension_count: int = 0



@dataclass
class IntLiteral(Expression):
    value: int


@dataclass
class BoolLiteral(Expression):
    value: bool


@dataclass
class NullLiteral(Expression):
    pass


@dataclass
class Name(Expression):
    name: str


@dataclass
class Unary(Expression):
    operator: str          # "-" or "!"
    operand: Expression


@dataclass
class Binary(Expression):
    operator: str          # "+", "==", "&&", ...
    left: Expression
    right: Expression


@dataclass
class Call(Expression):
    function_name: str
    arguments: List[Expression]


@dataclass
class FieldAccess(Expression):
    target_object: Expression
    field_name: str


@dataclass
class Index(Expression):
    array: Expression
    index: Expression


@dataclass
class NewObject(Expression):
    type: TypeRef          # a struct type


@dataclass
class NewArray(Expression):
    element_type: TypeRef
    size: Expression


# ---------- statements ----------
@dataclass
class Block(Statement):
    statements: List[Statement]


@dataclass
class VarDecl(Statement):
    name: str
    type: TypeRef
    init: Optional[Expression]


@dataclass
class Assign(Statement):
    target: Expression     # Name | FieldAccess | Index
    value: Expression


@dataclass
class IfStatement(Statement):
    condition: Expression
    then_block: Block
    else_block: Optional[Block]


@dataclass
class WhileStatement(Statement):
    condition: Expression
    body: Block


@dataclass
class ReturnStatement(Statement):
    value: Optional[Expression]


@dataclass
class PrintStatement(Statement):
    value: Expression


@dataclass
class ExpressionStatement(Statement):
    expression: Expression


# ---------- declarations ----------
@dataclass
class StructField(Node):
    name: str
    type: TypeRef


@dataclass
class StructDecl(Node):
    name: str
    fields: List[StructField]


@dataclass
class Param(Node):
    name: str
    type: TypeRef


@dataclass
class FunDecl(Node):
    name: str
    params: List[Param]
    return_type: TypeRef
    body: Block


@dataclass
class Program(Node):
    structs: List[StructDecl]
    functions: List[FunDecl]


if __name__ == "__main__":
    tree = Assign(
        target=Name("x"),
        value=Binary("+", Name("a"), Binary("*", IntLiteral(2), IntLiteral(3))),
    )
    print(tree)