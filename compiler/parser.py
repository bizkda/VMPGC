from lexer import lex, ToyError
from ast_nodes import *

# Binary operators: a higher number binds tighter.
BINARY_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "==": 3, "!=": 3,
    "<": 4, "<=": 4, ">": 4, ">=": 4,
    "+": 5, "-": 5,
    "*": 6, "/": 6, "%": 6,
}


class Parser:
    def __init__(self, source_code: str):
        self.tokens = lex(source_code)
        self.position = 0

    # =================================================================
    #  looking at tokens
    # =================================================================
    def current_token(self):
        """The token we are looking at (does not consume it)."""
        return self.tokens[self.position]

    def look_ahead(self, offset=1):
        """A later token, without consuming anything."""
        index = min(self.position + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def consume_token(self):
        """Return the current token and move to the next one."""
        consumed_token = self.current_token()
        if consumed_token.kind != "eof":
            self.position += 1
        return consumed_token

    # =================================================================
    #  checking what we have
    # =================================================================
    def is_operator(self, symbol: str) -> bool:
        """True if the current token is the operator `symbol`."""
        token = self.current_token()
        return token.kind == "operator" and token.value == symbol

    def is_keyword(self, word: str) -> bool:
        """True if the current token is the keyword `word`."""
        token = self.current_token()
        return token.kind == "keyword" and token.value == word

    # =================================================================
    #  consuming what we expect
    # =================================================================
    def match_operator(self, symbol: str) -> bool:
        """If the current token is `symbol`, consume it and return True.
        Otherwise do nothing and return False."""
        if self.is_operator(symbol):
            self.consume_token()
            return True
        return False

    def expect_operator(self, symbol: str):
        """Consume `symbol` and return its token, or raise an error."""
        if self.is_operator(symbol):
            return self.consume_token()
        self.error(f"expected '{symbol}', found {self.describe_current_token()}")

    def expect_keyword(self, word: str):
        """Consume the keyword `word` and return its token, or raise an error."""
        if self.is_keyword(word):
            return self.consume_token()
        self.error(f"expected '{word}', found {self.describe_current_token()}")

    def expect_identifier(self):
        """Consume any identifier and return its token, or raise an error."""
        if self.current_token().kind == "identifier":
            return self.consume_token()
        self.error(f"expected an identifier, found {self.describe_current_token()}")

    # =================================================================
    #  errors
    # =================================================================
    def describe_current_token(self) -> str:
        """Text for error messages."""
        token = self.current_token()
        if token.kind == "eof":
            return "end of file"
        return f"'{token.value}'"

    def error(self, message: str):
        token = self.current_token()
        raise ToyError(message, token.line, token.column)

    # =================================================================
    #  types
    # =================================================================
    def parse_base_type(self):
        """base_type = 'int' | 'bool' | IDENTIFIER      (without brackets)"""
        token = self.current_token()
        is_builtin_type = token.kind == "keyword" and token.value in ("int", "bool")
        is_struct_name = token.kind == "identifier"
        if is_builtin_type or is_struct_name:
            self.consume_token()
            return TypeRef(token.value, line=token.line, column=token.column)
        self.error(f"expected a type, found {self.describe_current_token()}")

    def parse_type(self):
        """type = base_type { '[' ']' }"""
        type_ref = self.parse_base_type()
        while self.match_operator("["):
            self.expect_operator("]")
            type_ref.dimension_count += 1
        return type_ref

    # =================================================================
    #  declarations
    # =================================================================
    def parse_program(self):
        """program = { struct_decl | fun_decl } EOF"""
        structs, functions = [], []
        while self.current_token().kind != "eof":
            if self.is_keyword("struct"):
                structs.append(self.parse_struct())
            elif self.is_keyword("fun"):
                functions.append(self.parse_function())
            else:
                self.error("expected 'struct' or 'fun', "
                           f"found {self.describe_current_token()}")
        return Program(structs, functions, line=1, column=1)

    def parse_struct(self):
        """struct_decl = 'struct' IDENTIFIER '{' { IDENTIFIER ':' type ';' } '}'"""
        start_token = self.expect_keyword("struct")
        struct_name = self.expect_identifier().value
        self.expect_operator("{")

        fields = []
        while not self.is_operator("}"):
            name_token = self.expect_identifier()
            self.expect_operator(":")
            field_type = self.parse_type()
            self.expect_operator(";")
            fields.append(StructField(name_token.value, field_type,
                                      line=name_token.line, column=name_token.column))

        self.expect_operator("}")
        return StructDecl(struct_name, fields,
                          line=start_token.line, column=start_token.column)

    def parse_parameter(self):
        """param = IDENTIFIER ':' type"""
        name_token = self.expect_identifier()
        self.expect_operator(":")
        parameter_type = self.parse_type()
        return Param(name_token.value, parameter_type,
                     line=name_token.line, column=name_token.column)

    def parse_parameter_list(self):
        """parameters = '(' [ param { ',' param } ] ')'"""
        self.expect_operator("(")
        parameters = []
        if not self.is_operator(")"):
            parameters.append(self.parse_parameter())
            while self.match_operator(","):
                parameters.append(self.parse_parameter())
        self.expect_operator(")")
        return parameters

    def parse_function(self):
        """fun_decl = 'fun' IDENTIFIER parameters ':' type block"""
        start_token = self.expect_keyword("fun")
        name = self.expect_identifier().value
        parameters = self.parse_parameter_list()
        self.expect_operator(":")
        return_type = self.parse_type()
        body = self.parse_block()
        return FunDecl(name, parameters, return_type, body,
                       line=start_token.line, column=start_token.column)

    # =================================================================
    #  statements
    # =================================================================
    def parse_block(self):
        """block = '{' { statement } '}'"""
        start_token = self.expect_operator("{")
        statements = []
        while not self.is_operator("}"):
            if self.current_token().kind == "eof":
                self.error("expected '}', found end of file")
            statements.append(self.parse_statement())
        self.expect_operator("}")
        return Block(statements, line=start_token.line, column=start_token.column)

    def parse_statement(self):
        """Look at the first token to decide which kind of statement this is."""
        if self.is_operator("{"):
            return self.parse_block()
        if self.is_keyword("var"):
            return self.parse_var_declaration()
        if self.is_keyword("if"):
            return self.parse_if()
        if self.is_keyword("while"):
            return self.parse_while()
        if self.is_keyword("return"):
            return self.parse_return()
        if self.is_keyword("print"):
            return self.parse_print()
        return self.parse_assignment_or_expression_statement()

    def parse_var_declaration(self):
        """var_decl = 'var' IDENTIFIER ':' type [ '=' expression ] ';'"""
        start_token = self.expect_keyword("var")
        name = self.expect_identifier().value
        self.expect_operator(":")
        declared_type = self.parse_type()
        initial_value = None
        if self.match_operator("="):
            initial_value = self.parse_expression()
        self.expect_operator(";")
        return VarDecl(name, declared_type, initial_value,
                       line=start_token.line, column=start_token.column)

    def parse_if(self):
        """if = 'if' '(' expression ')' block [ 'else' ( if | block ) ]"""
        start_token = self.expect_keyword("if")
        self.expect_operator("(")
        condition = self.parse_expression()
        self.expect_operator(")")
        then_block = self.parse_block()

        else_block = None
        if self.is_keyword("else"):
            else_token = self.consume_token()
            if self.is_keyword("if"):
                # `else if` : the else part is a block holding one if statement
                nested_if = self.parse_if()
                else_block = Block([nested_if],
                                   line=else_token.line, column=else_token.column)
            else:
                else_block = self.parse_block()
        return IfStatement(condition, then_block, else_block,
                           line=start_token.line, column=start_token.column)

    def parse_while(self):
        """while = 'while' '(' expression ')' block"""
        start_token = self.expect_keyword("while")
        self.expect_operator("(")
        condition = self.parse_expression()
        self.expect_operator(")")
        body = self.parse_block()
        return WhileStatement(condition, body,
                              line=start_token.line, column=start_token.column)

    def parse_return(self):
        """return = 'return' [ expression ] ';'"""
        start_token = self.expect_keyword("return")
        value = None
        if not self.is_operator(";"):
            value = self.parse_expression()
        self.expect_operator(";")
        return ReturnStatement(value,
                               line=start_token.line, column=start_token.column)

    def parse_print(self):
        """print = 'print' '(' expression ')' ';'"""
        start_token = self.expect_keyword("print")
        self.expect_operator("(")
        value = self.parse_expression()
        self.expect_operator(")")
        self.expect_operator(";")
        return PrintStatement(value,
                              line=start_token.line, column=start_token.column)

    def parse_assignment_or_expression_statement(self):
        """target '=' expression ';'   or   expression ';'

        We cannot tell which one it is until we have read the first
        expression and looked at the next token: '=' means assignment."""
        start_token = self.current_token()
        expression = self.parse_expression()

        if self.match_operator("="):
            if not isinstance(expression, (Name, FieldAccess, Index)):
                raise ToyError("invalid assignment target",
                               expression.line, expression.column)
            value = self.parse_expression()
            self.expect_operator(";")
            return Assign(expression, value,
                          line=start_token.line, column=start_token.column)

        self.expect_operator(";")
        return ExpressionStatement(expression,
                                   line=start_token.line, column=start_token.column)

    # =================================================================
    #  expressions
    # =================================================================
    def parse_expression(self, min_precedence=1):
        """Precedence climbing.

        Read one operand, then keep absorbing binary operators whose
        precedence is at least `min_precedence`. The right operand is read
        with a higher minimum, which makes operators left-associative:
        10 - 3 - 2 is (10 - 3) - 2."""
        left = self.parse_unary()
        while True:
            token = self.current_token()
            if token.kind != "operator":
                return left
            precedence = BINARY_PRECEDENCE.get(token.value, 0)
            if precedence < min_precedence:
                return left
            self.consume_token()
            right = self.parse_expression(precedence + 1)
            left = Binary(token.value, left, right,
                          line=token.line, column=token.column)

    def parse_unary(self):
        """unary = ( '-' | '!' ) unary | postfix"""
        token = self.current_token()
        if token.kind == "operator" and token.value in ("-", "!"):
            self.consume_token()
            operand = self.parse_unary()
            return Unary(token.value, operand,
                         line=token.line, column=token.column)
        return self.parse_postfix()

    def parse_postfix(self):
        """postfix = primary { '.' IDENTIFIER | '[' expression ']' }"""
        expression = self.parse_primary()
        while True:
            if self.is_operator("."):
                dot_token = self.consume_token()
                field_name = self.expect_identifier().value
                expression = FieldAccess(expression, field_name,
                                         line=dot_token.line, column=dot_token.column)
            elif self.is_operator("["):
                bracket_token = self.consume_token()
                index = self.parse_expression()
                self.expect_operator("]")
                expression = Index(expression, index,
                                   line=bracket_token.line, column=bracket_token.column)
            else:
                return expression

    def parse_primary(self):
        """primary = INTEGER | 'true' | 'false' | 'null' | new_expression
                   | IDENTIFIER [ '(' arguments ')' ] | '(' expression ')'"""
        token = self.current_token()

        if token.kind == "integer":
            self.consume_token()
            return IntLiteral(token.value, line=token.line, column=token.column)

        if self.is_keyword("true") or self.is_keyword("false"):
            self.consume_token()
            return BoolLiteral(token.value == "true",
                               line=token.line, column=token.column)

        if self.is_keyword("null"):
            self.consume_token()
            return NullLiteral(line=token.line, column=token.column)

        if self.is_keyword("new"):
            return self.parse_new_expression()

        if token.kind == "identifier":
            self.consume_token()
            if self.is_operator("("):
                arguments = self.parse_call_arguments()
                return Call(token.value, arguments,
                            line=token.line, column=token.column)
            return Name(token.value, line=token.line, column=token.column)

        if self.match_operator("("):
            expression = self.parse_expression()
            self.expect_operator(")")
            return expression

        self.error(f"expected an expression, found {self.describe_current_token()}")

    def parse_call_arguments(self):
        """arguments = '(' [ expression { ',' expression } ] ')'"""
        self.expect_operator("(")
        arguments = []
        if not self.is_operator(")"):
            arguments.append(self.parse_expression())
            while self.match_operator(","):
                arguments.append(self.parse_expression())
        self.expect_operator(")")
        return arguments

    def parse_new_expression(self):
        """new_expression = 'new' base_type [ '[' expression ']' ]

        new Node     -> NewObject          new int[10]  -> NewArray"""
        new_token = self.expect_keyword("new")
        base_type = self.parse_base_type()
        if self.match_operator("["):
            size = self.parse_expression()
            self.expect_operator("]")
            return NewArray(base_type, size,
                            line=new_token.line, column=new_token.column)
        if base_type.base_type in ("int", "bool"):
            raise ToyError("'new' needs a struct type or an array size",
                           new_token.line, new_token.column)
        return NewObject(base_type, line=new_token.line, column=new_token.column)


def parse(source_code: str) -> Program:
    """Parse a whole Toy program and return its AST."""
    return Parser(source_code).parse_program()
