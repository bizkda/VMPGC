"""Writing and reading the .tbc file (Toy ByteCode).

Layout (everything little-endian), as in section 8.3 of the specifications:

    magic            4 bytes   "TBC1"
    types            u32 count, then per type:
                       u8 kind, u32 field_count, u64 pointer_mask
    functions        u32 count, then per function:
                       u32 start, u32 parameter_count, u32 local_count,
                       u16 name length, the name bytes
                     then u32: index of main
    code             u32 count, then per instruction (8 bytes):
                       u8 opcode, 3 bytes of padding, i32 operand
    stack maps       u32 count, then per map:
                       u32 pc, u32 depth, u64 locals_mask, u64 stack_mask
"""
import struct

from compiler.backend.bytecode import OPCODES, OPCODE_LIST, Instruction, StackMap, TypeEntry
from compiler.backend.program import ProgramCode, FunctionInfo

MAGIC = b"TBC1"


class TbcError(ValueError):
    """The file is not a valid .tbc file."""


def to_bytes(program_code):
    out = bytearray(MAGIC)

    out += struct.pack("<I", len(program_code.types))
    for entry in program_code.types:
        out += struct.pack("<BIQ", entry.kind, entry.field_count, entry.pointer_mask)

    out += struct.pack("<I", len(program_code.functions))
    for function in program_code.functions:
        name = function.name.encode("utf-8")
        out += struct.pack("<IIIH", function.start, function.parameter_count,
                           function.local_count, len(name))
        out += name
    out += struct.pack("<I", program_code.main_index)

    out += struct.pack("<I", len(program_code.instructions))
    for instruction in program_code.instructions:
        out += struct.pack("<B3xi", OPCODES[instruction.opcode], instruction.operand)

    out += struct.pack("<I", len(program_code.stack_maps))
    for stack_map in program_code.stack_maps:
        out += struct.pack("<IIQQ", stack_map.pc, stack_map.depth,
                           stack_map.locals_mask, stack_map.stack_mask)
    return bytes(out)


class _Reader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def take(self, format_):
        size = struct.calcsize(format_)
        if self.position + size > len(self.data):
            raise TbcError("the file is truncated")
        values = struct.unpack_from(format_, self.data, self.position)
        self.position += size
        return values

    def take_bytes(self, count):
        if self.position + count > len(self.data):
            raise TbcError("the file is truncated")
        chunk = self.data[self.position:self.position + count]
        self.position += count
        return chunk


def from_bytes(data):
    reader = _Reader(data)
    if reader.take_bytes(4) != MAGIC:
        raise TbcError("not a .tbc file (bad magic number)")

    types = []
    (type_count,) = reader.take("<I")
    for type_id in range(1, type_count + 1):
        kind, field_count, pointer_mask = reader.take("<BIQ")
        types.append(TypeEntry(type_id, kind, f"type{type_id}", field_count, pointer_mask))

    functions = []
    (function_count,) = reader.take("<I")
    for _ in range(function_count):
        start, parameter_count, local_count, name_length = reader.take("<IIIH")
        name = reader.take_bytes(name_length).decode("utf-8")
        functions.append(FunctionInfo(name, start, parameter_count, local_count))
    (main_index,) = reader.take("<I")

    instructions = []
    (instruction_count,) = reader.take("<I")
    for _ in range(instruction_count):
        opcode_number, operand = reader.take("<B3xi")
        if not 1 <= opcode_number <= len(OPCODE_LIST):
            raise TbcError(f"invalid opcode {opcode_number}")
        instructions.append(Instruction(OPCODE_LIST[opcode_number - 1], operand))

    stack_maps = []
    (map_count,) = reader.take("<I")
    for _ in range(map_count):
        pc, depth, locals_mask, stack_mask = reader.take("<IIQQ")
        stack_maps.append(StackMap(pc, depth, locals_mask, stack_mask))

    if reader.position != len(data):
        raise TbcError("unexpected data at the end of the file")
    return ProgramCode(types, functions, instructions, stack_maps, main_index)


def write_tbc(program_code, path):
    with open(path, "wb") as output:
        output.write(to_bytes(program_code))


def read_tbc(path):
    with open(path, "rb") as source:
        return from_bytes(source.read())
