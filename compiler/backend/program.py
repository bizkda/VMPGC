"""Putting the compiled functions together into one program.

generate_program() takes the checked AST and returns a ProgramCode: the type
table, the function table, ONE flat array of instructions and the stack maps.
Jump targets and stack-map positions are then indices in that flat array.
"""
from dataclasses import dataclass

from compiler.frontend.parser import parse
from compiler.frontend.semantique import Checker
from compiler.backend.bytecode import Instruction, StackMap
from compiler.backend.codegen import TypeTable, FunctionGenerator


@dataclass
class FunctionInfo:
    name: str
    start: int              # index of the function's first instruction in the whole code
    parameter_count: int
    local_count: int        # parameters included


@dataclass
class ProgramCode:
    types: list             # list of TypeEntry, type_id = position + 1
    functions: list         # list of FunctionInfo
    instructions: list      # list of Instruction, all functions one after the other
    stack_maps: list        # list of StackMap (pc = index in `instructions`)
    main_index: int


def generate_program(program, checker):
    """Generate the code of every function and assemble the whole program."""
    type_table = TypeTable(program, checker.struct_fields)
    function_indexes = {f.name: i for i, f in enumerate(program.functions)}
    generator = FunctionGenerator(checker, type_table, function_indexes)

    functions, instructions, stack_maps = [], [], []
    start = 0
    for function in program.functions:
        code = generator.generate(function)
        functions.append(FunctionInfo(code.name, start, code.parameter_count, code.local_count))
        for instruction in code.instructions:
            operand = instruction.operand
            if instruction.opcode in ("JMP", "JZ"):
                operand += start            # function-relative -> position in the whole code
            instructions.append(Instruction(instruction.opcode, operand))
        for stack_map in code.stack_maps:
            stack_maps.append(StackMap(stack_map.pc + start, stack_map.depth,
                                       stack_map.locals_mask, stack_map.stack_mask))
        start += len(code.instructions)

    # array types are registered while the code is generated: read the table last
    return ProgramCode(list(type_table.entries), functions, instructions, stack_maps,
                       function_indexes["main"])


def compile_source(source_code):
    """Source text -> ProgramCode. Raises ToyError at the first error."""
    program = parse(source_code)
    checker = Checker(program)
    checker.check_program()
    return generate_program(program, checker)
