# Benchmark: Mark-and-Sweep and Stop-and-Copy

Produced by `python3 tests/benchmark.py`. Fastest of 3 runs, no heap verifier. The absolute numbers depend on the machine.

| program | heap | collector | collections | GC time (ms) | total time (ms) |
|---|---|---|---|---|---|
| bench_garbage | 256 KB | Mark-and-Sweep | 366 | 8.2 | 137 |
| bench_garbage | 256 KB | Stop-and-Copy | 732 | 0.1 | 107 |
| bench_garbage | 1 MB | Mark-and-Sweep | 91 | 9.3 | 140 |
| bench_garbage | 1 MB | Stop-and-Copy | 183 | 0.0 | 126 |
| bench_garbage | 8 MB | Mark-and-Sweep | 11 | 19.2 | 143 |
| bench_garbage | 8 MB | Stop-and-Copy | 22 | 0.0 | 116 |
| bench_live | 4 MB | Mark-and-Sweep | 24 | 20.1 | 110 |
| bench_live | 4 MB | Stop-and-Copy | 128 | 66.8 | 156 |
| bench_live | 8 MB | Mark-and-Sweep | 9 | 14.7 | 96 |
| bench_live | 8 MB | Stop-and-Copy | 24 | 12.5 | 86 |
| bench_live | 32 MB | Mark-and-Sweep | 2 | 24.9 | 113 |
| bench_live | 32 MB | Stop-and-Copy | 4 | 4.2 | 104 |
| bench_tree | 2 MB | Mark-and-Sweep | 14 | 5.9 | 51 |
| bench_tree | 2 MB | Stop-and-Copy | 98 | 16.7 | 62 |
| bench_tree | 8 MB | Mark-and-Sweep | 2 | 3.8 | 51 |
| bench_tree | 8 MB | Stop-and-Copy | 4 | 1.3 | 47 |
| bench_tree | 32 MB | Mark-and-Sweep | 0 | 0.0 | 49 |
| bench_tree | 32 MB | Stop-and-Copy | 1 | 0.7 | 50 |
