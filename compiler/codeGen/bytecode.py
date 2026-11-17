"""The bytecode: instructions, stack maps and the data a compiled function holds.

Everything here is plain data. The generator (codegen.py) fills it in,
the writer (step 3) saves it in a .tbc file, and the C VM reads it back.
"""
from dataclasses import dataclass, field

# ---------------------------------------------------------------------
#  opcodes
# ---------------------------------------------------------------------
OPCODE_LIST = [
    "PUSH_INT", "PUSH_NULL", "POP", "LOAD_LOCAL", "STORE_LOCAL",
    "ADD", "SUB", "MUL", "DIV", "MOD", "NEG", "NOT",
    "EQ", "NE", "LT", "LE", "GT", "GE",
    "JMP", "JZ", "CALL", "RET",
    "NEW", "NEW_ARRAY", "GETFIELD", "PUTFIELD", "ALOAD", "ASTORE",
    "PRINT_INT", "PRINT_BOOL",
]
OPCODES = {name: number for number, name in enumerate(OPCODE_LIST, start=1)}

# instructions that carry an operand (the others always have operand 0)
HAS_OPERAND = {"PUSH_INT", "LOAD_LOCAL", "STORE_LOCAL", "JMP", "JZ",
               "CALL", "NEW", "NEW_ARRAY", "GETFIELD", "PUTFIELD"}

# instructions where the GC may run: a stack map is recorded for each of them
SAFEPOINTS = {"NEW", "NEW_ARRAY", "CALL"}

# What each instruction does to the operand stack: (values popped, value pushed).
# pushed is "int" (not a reference), "ref" (a reference), None (nothing),
# or "dynamic" (it depends on a type: the generator says which).
# "dynamic" for pops means the number depends on the call.
EFFECTS = {
    "PUSH_INT": (0, "int"), "PUSH_NULL": (0, "ref"), "POP": (1, None),
    "LOAD_LOCAL": (0, "dynamic"), "STORE_LOCAL": (1, None),
    "ADD": (2, "int"), "SUB": (2, "int"), "MUL": (2, "int"),
    "DIV": (2, "int"), "MOD": (2, "int"), "NEG": (1, "int"), "NOT": (1, "int"),
    "EQ": (2, "int"), "NE": (2, "int"), "LT": (2, "int"),
    "LE": (2, "int"), "GT": (2, "int"), "GE": (2, "int"),
    "JMP": (0, None), "JZ": (1, None),
    "CALL": ("dynamic", "dynamic"), "RET": (1, None),
    "NEW": (0, "ref"), "NEW_ARRAY": (1, "ref"),
    "GETFIELD": (1, "dynamic"), "PUTFIELD": (2, None),
    "ALOAD": (2, "dynamic"), "ASTORE": (3, None),
    "PRINT_INT": (1, None), "PRINT_BOOL": (1, None),
}


@dataclass
class Instruction:
    opcode: str
    operand: int = 0     # signed 32 bits; a jump target is an instruction index

    def __str__(self):
        if self.opcode in HAS_OPERAND:
            return f"{self.opcode:<12} {self.operand}"
        return self.opcode


# ---------------------------------------------------------------------
#  stack maps
# ---------------------------------------------------------------------
@dataclass
class StackMap:
    """Which slots hold references at a safepoint (a bit is 1 for a reference).

    pc            index of the NEW / NEW_ARRAY / CALL instruction
    depth         number of values on the operand stack, after the instruction
                  has popped its operands (bit 0 of stack_mask = bottom of the stack)
    locals_mask   one bit per local variable of the function
    stack_mask    one bit per operand-stack slot
    """
    pc: int
    depth: int
    locals_mask: int
    stack_mask: int


# ---------------------------------------------------------------------
#  compiled functions and type descriptors
# ---------------------------------------------------------------------
@dataclass
class FunctionCode:
    name: str
    parameter_count: int
    local_count: int                  # parameters included
    local_types: list                 # the Toy type of every local slot
    instructions: list                # list of Instruction
    stack_maps: list                  # list of StackMap

    def dump(self):
        lines = [f"function {self.name}  (parameters={self.parameter_count}, "
                 f"locals={self.local_count})"]
        for index, instruction in enumerate(self.instructions):
            lines.append(f"  {index:3}  {instruction}")
        return "\n".join(lines)


STRUCT, ARRAY_OF_VALUES, ARRAY_OF_REFERENCES = 1, 2, 3


@dataclass
class TypeEntry:
    """Describes the layout of the objects of one type, for the GC."""
    type_id: int          # starts at 1; 0 is invalid
    kind: int             # STRUCT, ARRAY_OF_VALUES or ARRAY_OF_REFERENCES
    name: str             # for readable dumps only
    field_count: int      # structs only
    pointer_mask: int     # structs only: bit i is 1 if field i is a reference
