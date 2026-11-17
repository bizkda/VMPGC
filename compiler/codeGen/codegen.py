"""Code generator: turns the type-checked AST of a function into bytecode.

The generator keeps a model of the operand stack while it emits code: for each
value on the stack it knows whether it is a reference. That model is what lets
it write the stack map at every NEW, NEW_ARRAY and CALL.
"""
from compiler.language.lexer import ToyError
from compiler.language.ast_nodes import *
from compiler.language.toy_types import INT, BOOL, StructType, ArrayType, is_reference
from compiler.language.checker import always_returns
from compiler.codeGen.bytecode import (EFFECTS, SAFEPOINTS, Instruction, StackMap, FunctionCode,
                      TypeEntry, STRUCT, ARRAY_OF_VALUES, ARRAY_OF_REFERENCES)

INT32_MIN, INT32_MAX = -2 ** 31, 2 ** 31 - 1
MAX_LOCALS = 64            # limits fixed by the specifications (rule RG-06)
MAX_STACK_AT_SAFEPOINT = 64
MAX_STRUCT_FIELDS = 64

BINARY_OPCODES = {
    "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
    "==": "EQ", "!=": "NE", "<": "LT", "<=": "LE", ">": "GT", ">=": "GE",
}


# =====================================================================
#  type table
# =====================================================================
class TypeTable:
    """Gives every struct type and every array type a numeric type_id.

    Structs get ids 1, 2, 3... in declaration order. An array type gets the
    next free id the first time the generator needs it."""

    def __init__(self, program, struct_fields):
        self.entries = []
        self.ids = {}
        for struct in program.structs:
            fields = struct_fields[struct.name]
            if len(fields) > MAX_STRUCT_FIELDS:
                raise ToyError(f"struct '{struct.name}' has more than "
                               f"{MAX_STRUCT_FIELDS} fields", struct.line, struct.column)
            mask = sum(1 << i for i, t in enumerate(fields.values()) if is_reference(t))
            self._add(StructType(struct.name), STRUCT, struct.name, len(fields), mask)

    def _add(self, type_, kind, name, field_count, pointer_mask):
        type_id = len(self.entries) + 1
        self.entries.append(TypeEntry(type_id, kind, name, field_count, pointer_mask))
        self.ids[type_] = type_id

    def id_of(self, type_):
        """The type_id of a struct type or an array type (arrays are added on demand)."""
        if type_ not in self.ids:
            assert isinstance(type_, ArrayType), f"unknown type {type_}"
            kind = ARRAY_OF_REFERENCES if is_reference(type_.element) else ARRAY_OF_VALUES
            self._add(type_, kind, str(type_), 0, 0)
        return self.ids[type_]


# =====================================================================
#  function generator
# =====================================================================
class FunctionGenerator:
    def __init__(self, checker, type_table, function_indexes):
        self.checker = checker                      # struct fields, signatures
        self.type_table = type_table
        self.function_indexes = function_indexes    # function name -> index
        self.reset()

    def reset(self):
        self.instructions = []
        self.stack = []             # model of the operand stack: True = reference
        self.stack_maps = []
        self.local_types = []       # Toy type of each local slot
        self.scopes = []            # name -> slot, one dict per block
        self.position = (1, 1)      # where we are in the source, for error messages

    def error(self, message):
        raise ToyError(message, self.position[0], self.position[1])

    def at(self, node):
        self.position = (node.line, node.column)

    # -----------------------------------------------------------------
    #  emitting instructions
    # -----------------------------------------------------------------
    def emit(self, opcode, operand=0, *, pops=None, pushes_reference=None):
        """Append an instruction and update the model of the operand stack.

        `pops` and `pushes_reference` are only needed for the instructions whose
        effect depends on types: LOAD_LOCAL, GETFIELD, ALOAD and CALL."""
        default_pops, push_kind = EFFECTS[opcode]
        if pops is None:
            assert default_pops != "dynamic", f"{opcode} needs pops="
            pops = default_pops
        if push_kind == "dynamic":
            assert pushes_reference is not None, f"{opcode} needs pushes_reference="
            pushed = pushes_reference
        else:
            pushed = {"int": False, "ref": True, None: None}[push_kind]

        if not INT32_MIN <= operand <= INT32_MAX:
            self.error(f"operand {operand} does not fit in 32 bits")
        assert len(self.stack) >= pops, f"{opcode}: stack too small"

        if pops:
            del self.stack[len(self.stack) - pops:]
        index = len(self.instructions)
        self.instructions.append(Instruction(opcode, operand))
        if opcode in SAFEPOINTS:
            self.record_stack_map(index)       # state AFTER the operands are popped
        if pushed is not None:
            self.stack.append(pushed)
        return index

    def record_stack_map(self, pc):
        depth = len(self.stack)
        if depth > MAX_STACK_AT_SAFEPOINT:
            self.error(f"expression too complex: more than {MAX_STACK_AT_SAFEPOINT} "
                       "values on the stack at an allocation or a call")
        stack_mask = sum(1 << i for i, is_ref in enumerate(self.stack) if is_ref)
        # the locals mask is the same for the whole function: filled in at the end
        self.stack_maps.append(StackMap(pc, depth, 0, stack_mask))

    def emit_jump(self, opcode):
        """Emit a jump whose target is not known yet; patch it later."""
        return self.emit(opcode, -1)

    def patch_jump_to_here(self, jump_index):
        self.instructions[jump_index].operand = len(self.instructions)

    # -----------------------------------------------------------------
    #  local variables
    # -----------------------------------------------------------------
    def enter_scope(self):
        self.scopes.append({})

    def leave_scope(self):
        self.scopes.pop()

    def declare_local(self, name, type_):
        if len(self.local_types) >= MAX_LOCALS:
            self.error(f"function has more than {MAX_LOCALS} local variables")
        slot = len(self.local_types)       # every declaration gets its own slot
        self.local_types.append(type_)
        self.scopes[-1][name] = slot
        return slot

    def lookup_local(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise AssertionError(f"unknown variable {name!r}: the checker should have caught it")

    def field_index(self, struct_type, field_name):
        return list(self.checker.struct_fields[struct_type.name]).index(field_name)

    # -----------------------------------------------------------------
    #  a whole function
    # -----------------------------------------------------------------
    def generate(self, function):
        self.reset()
        self.at(function)
        self.enter_scope()
        for parameter in function.params:
            self.at(parameter)
            self.declare_local(parameter.name, parameter.resolved_type)
        self.generate_block(function.body)
        self.leave_scope()

        assert self.stack == [], "the operand stack must be empty at the end"
        for instruction in self.instructions:
            if instruction.opcode in ("JMP", "JZ"):
                assert 0 <= instruction.operand < len(self.instructions), "jump out of range"

        locals_mask = sum(1 << i for i, t in enumerate(self.local_types) if is_reference(t))
        for stack_map in self.stack_maps:
            stack_map.locals_mask = locals_mask
        return FunctionCode(function.name, len(function.params), len(self.local_types),
                            list(self.local_types), self.instructions, self.stack_maps)

    # -----------------------------------------------------------------
    #  statements
    # -----------------------------------------------------------------
    def generate_block(self, block):
        self.enter_scope()
        for statement in block.statements:
            self.generate_statement(statement)
        self.leave_scope()

    def generate_statement(self, statement):
        self.at(statement)
        assert self.stack == [], "a statement must start with an empty operand stack"

        if isinstance(statement, Block):
            self.generate_block(statement)

        elif isinstance(statement, VarDecl):
            declared_type = statement.resolved_type
            if statement.init is not None:
                self.generate_expression(statement.init)
            elif is_reference(declared_type):
                self.emit("PUSH_NULL")             # no value: the default is null
            else:
                self.emit("PUSH_INT", 0)           # ... or 0 / false
            self.at(statement)
            slot = self.declare_local(statement.name, declared_type)
            self.emit("STORE_LOCAL", slot)

        elif isinstance(statement, Assign):
            self.generate_assignment(statement)

        elif isinstance(statement, IfStatement):
            self.generate_if(statement)

        elif isinstance(statement, WhileStatement):
            loop_start = len(self.instructions)
            self.generate_expression(statement.condition)
            self.at(statement)
            jump_out = self.emit_jump("JZ")
            self.generate_block(statement.body)
            self.emit("JMP", loop_start)
            self.patch_jump_to_here(jump_out)

        elif isinstance(statement, ReturnStatement):
            self.generate_expression(statement.value)
            self.at(statement)
            self.emit("RET")

        elif isinstance(statement, PrintStatement):
            self.generate_expression(statement.value)
            self.at(statement)
            printer = "PRINT_BOOL" if statement.value.static_type == BOOL else "PRINT_INT"
            self.emit(printer)

        elif isinstance(statement, ExpressionStatement):
            self.generate_expression(statement.expression)
            self.at(statement)
            self.emit("POP")                       # the result of the call is not used

        else:
            raise AssertionError(f"unknown statement {type(statement).__name__}")

        assert self.stack == [], "a statement must leave the operand stack empty"

    def generate_assignment(self, statement):
        target = statement.target
        if isinstance(target, Name):
            self.generate_expression(statement.value)
            self.at(statement)
            self.emit("STORE_LOCAL", self.lookup_local(target.name))
        elif isinstance(target, FieldAccess):
            self.generate_expression(target.target_object)
            self.generate_expression(statement.value)
            self.at(statement)
            index = self.field_index(target.target_object.static_type, target.field_name)
            self.emit("PUTFIELD", index)
        elif isinstance(target, Index):
            self.generate_expression(target.array)
            self.generate_expression(target.index)
            self.generate_expression(statement.value)
            self.at(statement)
            self.emit("ASTORE")
        else:
            raise AssertionError(f"bad assignment target {type(target).__name__}")

    def generate_if(self, statement):
        self.generate_expression(statement.condition)
        self.at(statement)
        jump_over_then = self.emit_jump("JZ")
        self.generate_block(statement.then_block)

        if statement.else_block is None:
            self.patch_jump_to_here(jump_over_then)
            return

        jump_over_else = None
        if not always_returns(statement.then_block):    # otherwise the jump is never used
            jump_over_else = self.emit_jump("JMP")
        self.patch_jump_to_here(jump_over_then)
        self.generate_block(statement.else_block)
        if jump_over_else is not None:
            self.patch_jump_to_here(jump_over_else)

    # -----------------------------------------------------------------
    #  expressions
    # -----------------------------------------------------------------
    def generate_expression(self, node):
        self.at(node)

        if isinstance(node, IntLiteral):
            if node.value > INT32_MAX:
                self.error(f"integer literal too large (maximum {INT32_MAX})")
            self.emit("PUSH_INT", node.value)

        elif isinstance(node, BoolLiteral):
            self.emit("PUSH_INT", 1 if node.value else 0)

        elif isinstance(node, NullLiteral):
            self.emit("PUSH_NULL")

        elif isinstance(node, Name):
            slot = self.lookup_local(node.name)
            self.emit("LOAD_LOCAL", slot,
                      pushes_reference=is_reference(self.local_types[slot]))

        elif isinstance(node, Unary):
            self.generate_expression(node.operand)
            self.at(node)
            self.emit("NEG" if node.operator == "-" else "NOT")

        elif isinstance(node, Binary):
            self.generate_binary(node)

        elif isinstance(node, Call):
            for argument in node.arguments:
                self.generate_expression(argument)
            self.at(node)
            self.emit("CALL", self.function_indexes[node.function_name],
                      pops=len(node.arguments),
                      pushes_reference=is_reference(node.static_type))

        elif isinstance(node, FieldAccess):
            self.generate_expression(node.target_object)
            self.at(node)
            index = self.field_index(node.target_object.static_type, node.field_name)
            self.emit("GETFIELD", index, pushes_reference=is_reference(node.static_type))

        elif isinstance(node, Index):
            self.generate_expression(node.array)
            self.generate_expression(node.index)
            self.at(node)
            self.emit("ALOAD", pushes_reference=is_reference(node.static_type))

        elif isinstance(node, NewObject):
            self.emit("NEW", self.type_table.id_of(node.static_type))

        elif isinstance(node, NewArray):
            self.generate_expression(node.size)
            self.at(node)
            self.emit("NEW_ARRAY", self.type_table.id_of(node.static_type))

        else:
            raise AssertionError(f"unknown expression {type(node).__name__}")

    def generate_binary(self, node):
        if node.operator == "&&":
            # a && b :  if a is false the result is 0, otherwise it is b
            self.generate_expression(node.left)
            self.at(node)
            jump_if_false = self.emit_jump("JZ")
            stack_after_test = list(self.stack)
            self.generate_expression(node.right)
            self.at(node)
            jump_to_end = self.emit_jump("JMP")
            stack_at_end = list(self.stack)
            self.patch_jump_to_here(jump_if_false)
            self.stack = list(stack_after_test)        # the other path starts here
            self.emit("PUSH_INT", 0)
            assert self.stack == stack_at_end
            self.patch_jump_to_here(jump_to_end)

        elif node.operator == "||":
            # a || b :  if a is true the result is 1, otherwise it is b
            self.generate_expression(node.left)
            self.at(node)
            jump_to_right = self.emit_jump("JZ")
            stack_after_test = list(self.stack)
            self.emit("PUSH_INT", 1)
            jump_to_end = self.emit_jump("JMP")
            stack_at_end = list(self.stack)
            self.patch_jump_to_here(jump_to_right)
            self.stack = list(stack_after_test)
            self.generate_expression(node.right)
            assert self.stack == stack_at_end
            self.patch_jump_to_here(jump_to_end)

        else:
            self.generate_expression(node.left)
            self.generate_expression(node.right)
            self.at(node)
            self.emit(BINARY_OPCODES[node.operator])
