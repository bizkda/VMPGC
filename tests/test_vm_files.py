"""The VM must refuse damaged .tbc files cleanly (exit code 103), never crash.
Also checks the command line of the VM. Needs the VM to be built (make -C vm)."""
import copy
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

from compiler.backend.bytecode import OPCODES, Instruction, StackMap
from compiler.backend.program import compile_source
from compiler.backend.tbc import to_bytes

VM = next((p for p in (os.path.join(ROOT, "vm", "gcvm_asan"), os.path.join(ROOT, "vm", "gcvm"))
           if os.path.exists(p)), None)
ENVIRONMENT = dict(os.environ, ASAN_OPTIONS="exitcode=77:detect_leaks=1", UBSAN_OPTIONS="exitcode=78")


def run_vm(data=None, arguments=()):
    """Run the VM on `data` written to a temporary file."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "program.tbc")
        if data is not None:
            with open(path, "wb") as f:
                f.write(data)
        return subprocess.run([VM, path] + list(arguments), capture_output=True, text=True,
                              env=ENVIRONMENT, timeout=60)


def list_program():
    with open(os.path.join(HERE, "list.toy"), encoding="utf-8") as f:
        return compile_source(f.read())


def assert_refused(data, label):
    result = run_vm(data)
    assert result.returncode == 103, f"{label}: exit code {result.returncode}, stderr: {result.stderr[:200]}"
    assert result.stderr.startswith("gcvm:"), label


def test_every_truncation_is_refused():
    good = to_bytes(list_program())
    for length in range(len(good)):
        assert_refused(good[:length], f"truncated at {length}")


def test_wrong_files():
    good = to_bytes(list_program())
    assert_refused(b"XXXX" + good[4:], "bad magic")
    assert_refused(b"", "empty file")
    assert_refused(good + b"\0", "extra bytes")
    result = subprocess.run([VM, "/nonexistent/program.tbc"], capture_output=True, text=True, env=ENVIRONMENT)
    assert result.returncode == 103


def test_corrupted_content_is_refused():
    def mutated(change):
        program = copy.deepcopy(list_program())
        change(program)
        return to_bytes(program)

    instruction_at = lambda p, pc: p.instructions[pc]
    cases = {
        "jump out of the function": lambda p: setattr(instruction_at(p, 17), "operand", 999),
        "negative jump": lambda p: setattr(instruction_at(p, 17), "operand", -1),
        "jump into another function": lambda p: setattr(instruction_at(p, 17), "operand", 3),
        "call of a function that does not exist": lambda p: setattr(instruction_at(p, 20), "operand", 7),
        "local that does not exist": lambda p: setattr(instruction_at(p, 11), "operand", 50),
        "type that does not exist": lambda p: setattr(instruction_at(p, 0), "operand", 9),
        "negative field index": lambda p: setattr(instruction_at(p, 4), "operand", -1),
        "main does not exist": lambda p: setattr(p, "main_index", 5),
        "main with parameters": lambda p: setattr(p.functions[1], "parameter_count", 1),
        "functions out of order": lambda p: setattr(p.functions[1], "start", 0),
        "too many locals": lambda p: setattr(p.functions[0], "local_count", 65),
        "more parameters than locals": lambda p: setattr(p.functions[0], "parameter_count", 9),
        "missing stack map": lambda p: p.stack_maps.pop(),
        "two stack maps at one place": lambda p: p.stack_maps.append(StackMap(0, 0, 0b101, 0)),
        "stack map at a plain instruction": lambda p: setattr(p.stack_maps[0], "pc", 1),
        "stack map marks a missing local": lambda p: setattr(p.stack_maps[0], "locals_mask", 0b1000),
        "stack map too deep": lambda p: setattr(p.stack_maps[0], "depth", 65),
        "stack map bits beyond the depth": lambda p: setattr(p.stack_maps[0], "stack_mask", 0b10),
        "pointer mask beyond the fields": lambda p: setattr(p.types[0], "pointer_mask", 0b100),
        "unknown kind of type": lambda p: setattr(p.types[0], "kind", 9),
        "no functions": lambda p: (p.functions.clear(), setattr(p, "main_index", 0)),
    }
    for label, change in cases.items():
        assert_refused(mutated(change), label)


def test_invalid_opcode_is_refused():
    data = bytearray(to_bytes(list_program()))
    program = list_program()
    # find the first instruction in the file: after magic, types, functions, main index, count
    position = 4 + 4 + 13 + 4 + (14 + 4) * 2 + 4 + 4
    assert data[position] == OPCODES["NEW"]
    for bad_opcode in (0, 31, 255):
        damaged = bytearray(data)
        damaged[position] = bad_opcode
        assert_refused(bytes(damaged), f"opcode {bad_opcode}")


def test_command_line():
    good = to_bytes(list_program())
    for arguments, label in [(["--heap=abc"], "heap not a number"), (["--heap=10"], "heap too small"),
                             (["--heap=99999999999"], "heap too big"), (["--gc=other"], "unknown collector"),
                             (["--nothing"], "unknown option")]:
        result = run_vm(good, arguments)
        assert result.returncode == 1, f"{label}: exit code {result.returncode}"
        assert "usage" in result.stderr or "invalid heap" in result.stderr, label
    result = subprocess.run([VM], capture_output=True, text=True, env=ENVIRONMENT)
    assert result.returncode == 1 and "usage" in result.stderr


def test_a_tiny_heap_and_the_options_work():
    with open(os.path.join(HERE, "programs", "scoping.toy"), encoding="utf-8") as f:
        data = to_bytes(compile_source(f.read()))
    for arguments in (["--heap=1024"], ["--gc=copy", "--heap=1024"], ["--stress", "--heap=1024"],
                      ["--verify", "--gc-stats"]):
        result = run_vm(data, arguments)
        assert result.returncode == 0 and result.stdout == "11\ntrue\n0\n2\n4\n99\n", arguments


if __name__ == "__main__":
    if VM is None:
        print("skipped: the VM is not built (run `make -C vm`)")
        sys.exit(0)
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed (VM: {os.path.basename(VM)})")
