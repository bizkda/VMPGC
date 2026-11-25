#!/usr/bin/env python3
"""End-to-end tests: compile every program of tests/programs, run it on the VM, compare.

Each program is run with both collectors (Mark-and-Sweep and Stop-and-Copy), with the heap
verifier on, and, unless it says otherwise, again in stress mode (a collection before every
allocation). The output must be the same every time.

A program can say what it expects in comments at its top:
    // @heap N               heap size in bytes for the normal runs (default 8 MB)
    // @exit N               expected exit code (default 0)
    // @stderr TEXT          TEXT must appear on the error output
    // @expect-gc            at least one collection must have happened
    // @no-stress            do not run it in stress mode (too slow)
    // @stress-heap N        heap size for the stress runs (default 65536)
    // @compile-error TEXT   the compiler must refuse the program, with TEXT in its message
The expected standard output is in the file NAME.expected next to the program.

Usage:  python3 tests/run_programs.py [--asan] [--only NAME] [--quiet]
"""
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROGRAMS = os.path.join(ROOT, "tests", "programs")
TOYC = [sys.executable, os.path.join(ROOT, "compiler", "toyc.py")]
TIMEOUT = 300


def parse_directives(text):
    directives = {}
    for match in re.finditer(r"^//\s*@([a-z-]+)[ \t]*(.*)$", text, flags=re.M):
        directives[match.group(1)] = match.group(2).strip()
    return directives


def run(command):
    started = time.time()
    result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)
    return result, time.time() - started


def check_program(name, vm, work_dir):
    """Returns (list of problems, list of what was run)."""
    source_path = os.path.join(PROGRAMS, name + ".toy")
    with open(source_path, encoding="utf-8") as source_file:
        directives = parse_directives(source_file.read())
    expected_path = os.path.join(PROGRAMS, name + ".expected")
    expected_output = ""
    if os.path.exists(expected_path):
        with open(expected_path, encoding="utf-8") as expected_file:
            expected_output = expected_file.read()

    problems, ran = [], []
    tbc_path = os.path.join(work_dir, name + ".tbc")

    # ---------- the compiler ----------
    compiled, _ = run(TOYC + [source_path, "-o", tbc_path])
    if "compile-error" in directives:
        wanted = directives["compile-error"]
        if compiled.returncode != 1:
            problems.append(f"the compiler should refuse this program (exit code {compiled.returncode})")
        elif wanted not in compiled.stderr:
            problems.append(f"compiler message {compiled.stderr.strip()!r} does not contain {wanted!r}")
        if os.path.exists(tbc_path):
            problems.append("a .tbc file was written for a program with an error")
        return problems, ["compile"]
    if compiled.returncode != 0:
        return [f"compile error: {compiled.stderr.strip()}"], ["compile"]

    # ---------- the VM ----------
    wanted_exit = int(directives.get("exit", "0"))
    heap = directives.get("heap", str(8 * 1024 * 1024))
    stress_heap = directives.get("stress-heap", "65536")

    configurations = []
    for collector in ("ms", "copy"):
        configurations.append((collector, [f"--gc={collector}", f"--heap={heap}", "--verify", "--gc-stats"]))
    if "no-stress" not in directives:
        for collector in ("ms", "copy"):
            configurations.append((collector + "+stress",
                                   [f"--gc={collector}", f"--heap={stress_heap}", "--stress", "--gc-stats"]))

    for label, options in configurations:
        result, seconds = run([vm, tbc_path] + options)
        ran.append(label)
        if result.returncode != wanted_exit:
            problems.append(f"[{label}] exit code {result.returncode}, expected {wanted_exit}; stderr: {result.stderr.strip()[:300]}")
            continue
        if result.stdout != expected_output:
            problems.append(f"[{label}] the output is different from {name}.expected "
                            f"(got {len(result.stdout.splitlines())} lines, expected {len(expected_output.splitlines())})")
            continue
        if "stderr" in directives and directives["stderr"] not in result.stderr:
            problems.append(f"[{label}] stderr does not contain {directives['stderr']!r}: {result.stderr.strip()[:300]}")
            continue
        if "expect-gc" in directives and "stress" not in label:
            collections = re.search(r"collectes=(\d+)", result.stderr)
            if not collections or int(collections.group(1)) == 0:
                problems.append(f"[{label}] no collection happened, but this test is meant to need the GC")
    return problems, ran


def main(arguments):
    use_asan = "--asan" in arguments
    quiet = "--quiet" in arguments
    only = arguments[arguments.index("--only") + 1] if "--only" in arguments else None

    vm = os.path.join(ROOT, "vm", "gcvm_asan" if use_asan else "gcvm")
    if not os.path.exists(vm):
        print(f"{vm} does not exist: run `make -C vm{' debug' if use_asan else ''}` first")
        return 2
    if use_asan:
        os.environ.setdefault("ASAN_OPTIONS", "detect_leaks=1")

    names = sorted(f[:-4] for f in os.listdir(PROGRAMS) if f.endswith(".toy"))
    if only:
        names = [n for n in names if n == only]
    failures = 0
    with tempfile.TemporaryDirectory() as work_dir:
        for name in names:
            started = time.time()
            problems, ran = check_program(name, vm, work_dir)
            seconds = time.time() - started
            if problems:
                failures += 1
                print(f"FAIL  {name}")
                for problem in problems:
                    print(f"        {problem}")
            elif not quiet:
                print(f"ok    {name:<20} {' '.join(ran):<36} {seconds:5.1f}s")
    print(f"\n{len(names) - failures} of {len(names)} programs passed"
          f"{' (with AddressSanitizer)' if use_asan else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
