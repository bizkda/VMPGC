import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))   # the project root

from compiler.backend.program import compile_source
from compiler.backend.disassembler import format_program


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as source_file:
        return source_file.read()


def test_function_table_and_main():
    program = compile_source(read("list.toy"))
    assert [(f.name, f.start, f.parameter_count, f.local_count) for f in program.functions] == [
        ("push", 0, 2, 3), ("main", 10, 0, 2)]
    assert program.main_index == 1
    assert len(program.instructions) == 32


def test_jumps_and_maps_use_positions_in_the_whole_code():
    program = compile_source(read("list.toy"))
    jumps = [(i, ins.opcode, ins.operand) for i, ins in enumerate(program.instructions)
             if ins.opcode in ("JMP", "JZ")]
    assert jumps == [(17, "JZ", 27), (26, "JMP", 14)]          # main starts at 10: both are > 10
    assert [(m.pc, m.depth, m.locals_mask, m.stack_mask) for m in program.stack_maps] == [
        (0, 0, 0b101, 0),       # NEW in push
        (20, 0, 0b01, 0)]       # CALL push in main (only `list` is a reference)
    assert program.instructions[20].operand == 0               # CALL push: the index of push


def test_type_table():
    program = compile_source(read("arrays.toy"))
    assert [(t.type_id, t.name) for t in program.types] == [(1, "Tree"), (2, "int[]"), (3, "Tree[]")]


def test_dump_is_readable():
    text = format_program(compile_source(read("list.toy")))
    assert "1  Node  (struct, 2 fields, pointer mask 0b10)" in text
    assert "<- entry point" in text
    assert "CALL         0     ; push | stack map: locals=0b01 stack=- depth=0" in text
    assert "NEW          1     ; Node | stack map: locals=0b101 stack=- depth=0" in text


def test_every_example_program_compiles():
    for path in glob.glob(os.path.join(HERE, "programs", "*.toy")):
        with open(path, encoding="utf-8") as source_file:
            source = source_file.read()
        if "@compile-error" in source:
            continue
        program = compile_source(source)
        assert program.functions[program.main_index].name == "main", path
        for stack_map in program.stack_maps:
            assert program.instructions[stack_map.pc].opcode in ("NEW", "NEW_ARRAY", "CALL"), path


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
