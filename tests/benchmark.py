#!/usr/bin/env python3
"""Compare Mark-and-Sweep and Stop-and-Copy on the programs of tests/bench.

Each configuration is run 3 times (without the verifier) and the fastest run is kept.
The numbers depend on the machine: what matters is how the two collectors compare.

Usage:  python3 tests/benchmark.py [--output docs/benchmark.md]
"""
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
VM = os.path.join(ROOT, "vm", "gcvm")
TOYC = [sys.executable, os.path.join(ROOT, "compiler", "toyc.py")]
MB = 1024 * 1024

# program -> heap sizes to try
PROGRAMS = {
    "bench_garbage": [256 * 1024, 1 * MB, 8 * MB],
    "bench_live": [4 * MB, 8 * MB, 32 * MB],
    "bench_tree": [2 * MB, 8 * MB, 32 * MB],
}


def measure(tbc, collector, heap):
    best = None
    for _ in range(3):
        started = time.time()
        result = subprocess.run([VM, tbc, f"--gc={collector}", f"--heap={heap}", "--gc-stats"],
                                capture_output=True, text=True)
        total_ms = (time.time() - started) * 1000
        if result.returncode != 0:
            return None, result.stdout
        stats = re.search(r"collectes=(\d+).*octets_recuperes=(\d+) temps_gc_ms=([\d.]+)", result.stderr)
        run = (total_ms, int(stats.group(1)), float(stats.group(3)), result.stdout)
        if best is None or run[0] < best[0]:
            best = run
    return best[:3], best[3]


def main(arguments):
    if not os.path.exists(VM):
        print("build the VM first: make -C vm")
        return 2
    lines = ["| program | heap | collector | collections | GC time (ms) | total time (ms) |",
             "|---|---|---|---|---|---|"]
    with tempfile.TemporaryDirectory() as folder:
        for name, heaps in PROGRAMS.items():
            tbc = os.path.join(folder, name + ".tbc")
            subprocess.run(TOYC + [os.path.join(ROOT, "tests", "bench", name + ".toy"), "-o", tbc], check=True)
            for heap in heaps:
                outputs = set()
                for collector, label in (("ms", "Mark-and-Sweep"), ("copy", "Stop-and-Copy")):
                    measured, output = measure(tbc, collector, heap)
                    size = f"{heap // 1024} KB" if heap < MB else f"{heap // MB} MB"
                    if measured is None:
                        lines.append(f"| {name} | {size} | {label} | out of memory | | |")
                        continue
                    outputs.add(output)
                    total_ms, collections, gc_ms = measured
                    lines.append(f"| {name} | {size} | {label} | {collections} | {gc_ms:.1f} | {total_ms:.0f} |")
                assert len(outputs) <= 1, f"{name}: the two collectors gave different outputs"
    table = "\n".join(lines)
    print(table)
    if "--output" in arguments:
        path = arguments[arguments.index("--output") + 1]
        with open(path, "w", encoding="utf-8") as output_file:
            output_file.write("# Benchmark: Mark-and-Sweep and Stop-and-Copy\n\n"
                              "Produced by `python3 tests/benchmark.py`. Fastest of 3 runs, no heap verifier. "
                              "The absolute numbers depend on the machine.\n\n" + table + "\n")
        print(f"\nwritten to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
