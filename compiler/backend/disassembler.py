"""Readable text for a compiled program (the --dump option of toyc)."""
from compiler.backend.bytecode import SAFEPOINTS, STRUCT, ARRAY_OF_VALUES, ARRAY_OF_REFERENCES

KIND_NAMES = {STRUCT: "struct", ARRAY_OF_VALUES: "array of values",
              ARRAY_OF_REFERENCES: "array of references"}


def format_mask(mask, width):
    """Binary text of a mask, '-' when there is nothing to show."""
    return f"0b{mask:0{width}b}" if width else "-"


def format_program(program_code):
    types = program_code.types
    maps_by_pc = {m.pc: m for m in program_code.stack_maps}
    lines = []

    lines.append("== types ==")
    for entry in types:
        detail = ""
        if entry.kind == STRUCT:
            detail = (f", {entry.field_count} fields, "
                      f"pointer mask {format_mask(entry.pointer_mask, entry.field_count)}")
        lines.append(f"  {entry.type_id:3}  {entry.name}  ({KIND_NAMES[entry.kind]}{detail})")

    lines.append("")
    lines.append("== functions ==")
    for index, function in enumerate(program_code.functions):
        main = "   <- entry point" if index == program_code.main_index else ""
        lines.append(f"  {index:3}  {function.name}  start={function.start} "
                     f"parameters={function.parameter_count} locals={function.local_count}{main}")

    lines.append("")
    lines.append("== code ==")
    for index, function in enumerate(program_code.functions):
        end = (program_code.functions[index + 1].start
               if index + 1 < len(program_code.functions) else len(program_code.instructions))
        lines.append(f"function {function.name}")
        for pc in range(function.start, end):
            instruction = program_code.instructions[pc]
            notes = []
            if instruction.opcode == "CALL":
                notes.append(program_code.functions[instruction.operand].name)
            elif instruction.opcode in ("NEW", "NEW_ARRAY"):
                notes.append(types[instruction.operand - 1].name)
            if instruction.opcode in SAFEPOINTS:
                stack_map = maps_by_pc[pc]
                notes.append(f"stack map: locals={format_mask(stack_map.locals_mask, function.local_count)}"
                             f" stack={format_mask(stack_map.stack_mask, stack_map.depth)}"
                             f" depth={stack_map.depth}")
            comment = ("   ; " + " | ".join(notes)) if notes else ""
            lines.append(f"  {pc:4}  {str(instruction):<16}{comment}".rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
