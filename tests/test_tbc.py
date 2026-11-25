import glob
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

from compiler.backend.bytecode import OPCODES, OPCODE_LIST
from compiler.backend.program import compile_source
from compiler.backend.tbc import to_bytes, from_bytes, TbcError


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as source_file:
        return source_file.read()


def test_round_trip_of_every_program():
    for path in glob.glob(os.path.join(HERE, "programs", "*.toy")) + [os.path.join(HERE, "list.toy")]:
        with open(path, encoding="utf-8") as source_file:
            source = source_file.read()
        if "@compile-error" in source:
            continue
        program = compile_source(source)
        data = to_bytes(program)
        back = from_bytes(data)
        assert back.functions == program.functions, path
        assert back.instructions == program.instructions, path
        assert back.stack_maps == program.stack_maps, path
        assert back.main_index == program.main_index, path
        assert [(t.kind, t.field_count, t.pointer_mask) for t in back.types] == \
               [(t.kind, t.field_count, t.pointer_mask) for t in program.types], path
        assert to_bytes(back) == data, path             # writing again gives the same bytes


def test_layout_matches_the_specifications():
    program = compile_source(read("list.toy"))
    data = to_bytes(program)
    assert data[:4] == b"TBC1"
    assert struct.unpack_from("<I", data, 4) == (1,)                     # one type
    assert struct.unpack_from("<BIQ", data, 8) == (1, 2, 0b10)           # struct, 2 fields, mask 10
    position = 8 + 13
    assert struct.unpack_from("<I", data, position) == (2,)              # two functions
    position += 4
    assert struct.unpack_from("<IIIH", data, position) == (0, 2, 3, 4)   # push: start, params, locals, name length
    assert data[position + 14:position + 18] == b"push"
    position += 18
    assert struct.unpack_from("<IIIH", data, position) == (10, 0, 2, 4)  # main
    position += 18
    assert struct.unpack_from("<I", data, position) == (1,)              # index of main
    position += 4
    assert struct.unpack_from("<I", data, position) == (32,)             # instruction count
    position += 4
    # first instruction: NEW 1 = opcode byte, 3 bytes of padding, int32 operand
    assert data[position] == OPCODES["NEW"] and data[position + 1:position + 4] == b"\0\0\0"
    assert struct.unpack_from("<i", data, position + 4) == (1,)
    position += 32 * 8
    assert struct.unpack_from("<I", data, position) == (2,)              # two stack maps
    assert struct.unpack_from("<IIQQ", data, position + 4) == (0, 0, 0b101, 0)
    assert len(data) == position + 4 + 2 * 24


def test_bad_files_are_refused():
    good = to_bytes(compile_source(read("list.toy")))
    cases = {
        "bad magic": b"XXXX" + good[4:],
        "empty": b"",
        "extra bytes": good + b"\0",
    }
    for label, data in cases.items():
        try:
            from_bytes(data)
        except TbcError:
            continue
        raise AssertionError(f"{label}: should have been refused")
    for length in range(len(good)):                     # every truncation
        try:
            from_bytes(good[:length])
        except TbcError:
            continue
        raise AssertionError(f"truncation at {length} bytes should have been refused")


def test_opcodes_header_of_the_vm_matches_the_compiler():
    with open(os.path.join(ROOT, "vm", "opcodes.h"), encoding="utf-8") as header:
        found = re.findall(r"OP_([A-Z_]+)\s*=\s*(\d+)", header.read())
    assert [(name, int(number)) for name, number in found] == \
           [(name, number) for number, name in enumerate(OPCODE_LIST, start=1)]


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
