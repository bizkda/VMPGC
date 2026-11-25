import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TOYC = [sys.executable, os.path.join(ROOT, "compiler", "toyc.py")]


def run(arguments):
    return subprocess.run(TOYC + arguments, capture_output=True, text=True)


def test_compiles_and_writes_the_file():
    with tempfile.TemporaryDirectory() as folder:
        output = os.path.join(folder, "out.tbc")
        result = run([os.path.join(HERE, "list.toy"), "-o", output])
        assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
        with open(output, "rb") as written:
            assert written.read(4) == b"TBC1"


def test_default_output_name():
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, "prog.toy")
        with open(source, "w", encoding="utf-8") as f:
            f.write("fun main(): int { return 0; }")
        assert run([source]).returncode == 0
        assert os.path.exists(os.path.join(folder, "prog.tbc"))


def test_dump_prints_the_bytecode():
    with tempfile.TemporaryDirectory() as folder:
        result = run([os.path.join(HERE, "list.toy"), "-o", os.path.join(folder, "x.tbc"), "--dump"])
        assert result.returncode == 0
        assert "function push" in result.stdout and "PUTFIELD" in result.stdout


def test_error_gives_position_exit_code_1_and_no_file():
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, "bad.toy")
        with open(source, "w", encoding="utf-8") as f:
            f.write("fun main(): int {\n    var x: int = true;\n    return 0;\n}\n")
        result = run([source])
        assert result.returncode == 1
        assert result.stderr.strip() == f"{source}:2:18: type mismatch: expected int, found bool"
        assert not os.path.exists(os.path.join(folder, "bad.tbc"))


def test_usage_errors():
    assert run([]).returncode == 1
    assert run(["a.toy", "b.toy"]).returncode == 1
    assert run(["--nothing"]).returncode == 1
    assert run(["/nonexistent/file.toy"]).returncode == 1


if __name__ == "__main__":
    count = 0
    for name, function in list(globals().items()):
        if name.startswith("test_"):
            function()
            count += 1
            print("ok", name)
    print(f"\n{count} tests passed")
