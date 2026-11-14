from lexer import ToyError
from ast_nodes import *
from toy_types import INT, BOOL, NULL, StructType, ArrayType, is_reference, is_compatible


class FunctionSignature:
    def __init__(self, name, parameter_types, return_type):
        self.name = name
        self.parameter_types = parameter_types
        self.return_type = return_type


class Checker:
    def __init__(self, program):
        self.program = program
        self.struct_fields = {}      # struct name -> {field name: type}
        self.functions = {}          # function name -> FunctionSignature
        self.scopes = []             # a stack of dicts: variable name -> type
        self.current_return_type = None

    def error(self, message, node):
        raise ToyError(message, node.line, node.column)

    def require_compatible(self, actual, expected, node):
        """Raise a type mismatch error unless `actual` can be used as `expected`."""
        if not is_compatible(actual, expected):
            self.error(f"type mismatch: expected {expected}, found {actual}", node)

    # =================================================================
    #  types
    # =================================================================
    def resolve_type(self, type_ref):
        """TypeRef('Node', dimension_count=1)  ->  ArrayType(StructType('Node'))"""
        if type_ref.dimension_count > 1:
            self.error("arrays of arrays are not supported", type_ref)

        if type_ref.base_type == "int":
            base_type = INT
        elif type_ref.base_type == "bool":
            base_type = BOOL
        elif type_ref.base_type in self.struct_fields:
            base_type = StructType(type_ref.base_type)
        else:
            self.error(f"unknown type '{type_ref.base_type}'", type_ref)

        if type_ref.dimension_count == 1:
            return ArrayType(base_type)
        return base_type

    # =================================================================
    #  pass 1: structs and functions
    # =================================================================
    def collect_declarations(self):
        # record every struct name first, so structs can refer to each other
        for struct in self.program.structs:
            if struct.name in self.struct_fields:
                self.error(f"duplicate struct '{struct.name}'", struct)
            self.struct_fields[struct.name] = {}

        # now that all names are known, resolve the fields
        for struct in self.program.structs:
            fields = self.struct_fields[struct.name]
            for field in struct.fields:
                if field.name in fields:
                    self.error(f"duplicate field '{field.name}' in struct '{struct.name}'", field)
                fields[field.name] = self.resolve_type(field.type)

        # function signatures (a function can call one declared later)
        for function in self.program.functions:
            if function.name in self.functions:
                self.error(f"duplicate function '{function.name}'", function)
            parameter_types = [self.resolve_type(p.type) for p in function.params]
            return_type = self.resolve_type(function.return_type)
            self.functions[function.name] = FunctionSignature(
                function.name, parameter_types, return_type)

        # main must exist, take no parameters and return int
        main_node = next((f for f in self.program.functions if f.name == "main"), None)
        if main_node is None:
            raise ToyError("missing function 'main'", 1, 1)
        main_signature = self.functions["main"]
        if main_signature.parameter_types or main_signature.return_type != INT:
            self.error("'main' must have no parameters and return int", main_node)

    # =================================================================
    #  scopes
    # =================================================================
    def enter_scope(self):
        self.scopes.append({})

    def leave_scope(self):
        self.scopes.pop()

    def declare_variable(self, name, type_, node):
        """Add a variable to the innermost scope (no masking, rule RG-03)."""
        for scope in reversed(self.scopes):
            if name in scope:
                self.error(f"duplicate declaration of '{name}'", node)
        self.scopes[-1][name] = type_

    def lookup_variable(self, name, node):
        """Find the type of a visible variable, searching the innermost scope first."""
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        self.error(f"undefined variable '{name}'", node)

    # =================================================================
    #  expressions
    # =================================================================
    def check_expression(self, node):
        """Compute the type of `node`, store it in node.static_type and return it."""
        node.static_type = self.type_of_expression(node)
        return node.static_type

    def type_of_expression(self, node):
        if isinstance(node, IntLiteral):
            return INT
        elif isinstance(node, BoolLiteral):
            return BOOL
        elif isinstance(node, NullLiteral):
            return NULL
        elif isinstance(node, Name):
            return self.lookup_variable(node.name, node)
        elif isinstance(node, Unary):
            operand_type = self.check_expression(node.operand)
            if node.operator == "!":
                if operand_type != BOOL:
                    self.error(f"operator '!' requires a bool, not {operand_type}", node)
                return BOOL
            elif node.operator == "-":
                if operand_type != INT:
                    self.error(f"operator '-' requires an int, not {operand_type}", node)
                return INT
            else:
                raise AssertionError(f"unknown unary operator {node.operator!r}")
        elif isinstance(node, Binary):
            left_type = self.check_expression(node.left)
            right_type = self.check_expression(node.right)
            if node.operator in ("+", "-", "*", "/", "%"):
                if left_type != INT or right_type != INT:
                    self.error(f"operator '{node.operator}' requires two ints, not {left_type} and {right_type}", node)
                return INT
            elif node.operator in ("==", "!="):
                # compatible in either direction: `p == null` and `null == p`
                if not (is_compatible(left_type, right_type) or is_compatible(right_type, left_type)):
                    self.error(f"operator '{node.operator}' requires compatible types, not {left_type} and {right_type}", node)
                return BOOL
            elif node.operator in ("<", "<=", ">", ">="):
                if left_type != INT or right_type != INT:
                    self.error(f"operator '{node.operator}' requires two ints, not {left_type} and {right_type}", node)
                return BOOL
            elif node.operator in ("&&", "||"):
                if left_type != BOOL or right_type != BOOL:
                    self.error(f"operator '{node.operator}' requires two bools, not {left_type} and {right_type}", node)
                return BOOL
            else:
                raise AssertionError(f"unknown binary operator {node.operator!r}")
        elif isinstance(node, Call):
            signature = self.functions.get(node.function_name)
            if signature is None:
                self.error(f"undefined function '{node.function_name}'", node)
            expected_count = len(signature.parameter_types)
            if len(node.arguments) != expected_count:
                self.error(f"wrong number of arguments for '{node.function_name}': "
                           f"expected {expected_count}, found {len(node.arguments)}", node)
            for argument, expected_type in zip(node.arguments, signature.parameter_types):
                self.require_compatible(self.check_expression(argument), expected_type, argument)
            return signature.return_type
        elif isinstance(node, FieldAccess):
            object_type = self.check_expression(node.target_object)
            if not isinstance(object_type, StructType):
                self.error(f"cannot access field '{node.field_name}' of {object_type}", node)
            fields = self.struct_fields[object_type.name]
            if node.field_name not in fields:
                self.error(f"unknown field '{node.field_name}' in struct '{object_type.name}'", node)
            return fields[node.field_name]
        elif isinstance(node, Index):
            array_type = self.check_expression(node.array)
            index_type = self.check_expression(node.index)
            if not isinstance(array_type, ArrayType):
                self.error(f"cannot index {array_type}", node)
            if index_type != INT:
                self.error(f"array index must be an int, not {index_type}", node.index)
            return array_type.element
        elif isinstance(node, NewObject):
            return self.resolve_type(node.type)
        elif isinstance(node, NewArray):
            element_type = self.resolve_type(node.element_type)
            size_type = self.check_expression(node.size)
            if size_type != INT:
                self.error(f"array size must be an int, not {size_type}", node.size)
            return ArrayType(element_type)
        else:
            self.error(f"cannot check {type(node).__name__} yet", node)

    # =================================================================
    #  statements
    # =================================================================
    def check_block(self, block):
        """A block opens a scope: its variables disappear at the closing brace."""
        self.enter_scope()
        for statement in block.statements:
            self.check_statement(statement)
        self.leave_scope()

    def check_condition(self, expression):
        condition_type = self.check_expression(expression)
        if condition_type != BOOL:
            self.error(f"condition must be a bool, not {condition_type}", expression)

    def check_statement(self, statement):
        if isinstance(statement, Block):
            self.check_block(statement)

        elif isinstance(statement, VarDecl):
            declared_type = self.resolve_type(statement.type)
            if statement.init is not None:
                # the initial value is checked BEFORE the variable exists,
                # so `var x: int = x;` is an error
                init_type = self.check_expression(statement.init)
                self.require_compatible(init_type, declared_type, statement.init)
            statement.resolved_type = declared_type
            self.declare_variable(statement.name, declared_type, statement)

        elif isinstance(statement, Assign):
            target_type = self.check_expression(statement.target)
            value_type = self.check_expression(statement.value)
            self.require_compatible(value_type, target_type, statement.value)

        elif isinstance(statement, IfStatement):
            self.check_condition(statement.condition)
            self.check_block(statement.then_block)
            if statement.else_block is not None:
                self.check_block(statement.else_block)

        elif isinstance(statement, WhileStatement):
            self.check_condition(statement.condition)
            self.check_block(statement.body)

        elif isinstance(statement, ReturnStatement):
            if statement.value is None:
                self.error("return requires a value", statement)
            value_type = self.check_expression(statement.value)
            self.require_compatible(value_type, self.current_return_type, statement.value)

        elif isinstance(statement, PrintStatement):
            value_type = self.check_expression(statement.value)
            if value_type not in (INT, BOOL):
                self.error(f"print requires an int or a bool, not {value_type}", statement)

        elif isinstance(statement, ExpressionStatement):
            if not isinstance(statement.expression, Call):
                self.error("only a call can be used as a statement", statement)
            self.check_expression(statement.expression)

        else:
            raise AssertionError(f"unknown statement {type(statement).__name__}")

    # =================================================================
    #  functions and the whole program
    # =================================================================
    def always_returns(self, statement):
        """True if every path through `statement` ends with a return.
        Conservative: a while loop is assumed to possibly never run."""
        if isinstance(statement, ReturnStatement):
            return True
        if isinstance(statement, Block):
            return any(self.always_returns(inner) for inner in statement.statements)
        if isinstance(statement, IfStatement):
            return (statement.else_block is not None
                    and self.always_returns(statement.then_block)
                    and self.always_returns(statement.else_block))
        return False

    def check_function(self, function):
        signature = self.functions[function.name]
        self.current_return_type = signature.return_type

        self.enter_scope()
        for parameter, parameter_type in zip(function.params, signature.parameter_types):
            parameter.resolved_type = parameter_type
            self.declare_variable(parameter.name, parameter_type, parameter)
        self.check_block(function.body)
        self.leave_scope()

        if not self.always_returns(function.body):
            self.error(f"missing return in function '{function.name}'", function)

    def check_program(self):
        """Check the whole program. Raises ToyError at the first problem."""
        self.collect_declarations()
        for function in self.program.functions:
            self.check_function(function)
        return self.program


def check(program):
    """Type-check `program` (an AST). Returns it, with types filled in."""
    return Checker(program).check_program()
