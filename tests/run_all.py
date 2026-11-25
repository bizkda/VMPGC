#!/usr/bin/env python3
"""Run every test of the project: unit tests, then the end-to-end programs.

Usage:  python3 tests/run_all.py [--asan]

With --asan the VM is built with AddressSanitizer and UndefinedBehaviorSanitizer and used for
the end-to-end programs and the damaged-file tests.
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def main(arguments):
    use_asan = "--asan" in arguments
    build = subprocess.run(["make", "-s", "-C", os.path.join(ROOT, "vm"), "debug" if use_asan else "gcvm"])
    if build.returncode != 0:
        print("the VM does not build")
        return 1

    failed = []
    unit_tests = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    print(f"{'test file':<24}result")
    for path in unit_tests:
        name = os.path.basename(path)
        result = subprocess.run([sys.executable, path], capture_output=True, text=True)
        last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if result.returncode == 0:
            print(f"{name:<24}ok   {last_line}")
        else:
            print(f"{name:<24}FAIL")
            print(result.stdout[-1500:], result.stderr[-1500:])
            failed.append(name)

    print("\nend-to-end programs (compile, run on both collectors, verifier, stress mode):")
    programs = subprocess.run([sys.executable, os.path.join(HERE, "run_programs.py"), "--quiet"]
                              + (["--asan"] if use_asan else []))
    if programs.returncode != 0:
        failed.append("run_programs.py")

    print()
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("everything passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
