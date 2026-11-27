# VMPGC

A compiler (Python) and a bytecode virtual machine (C) with a **precise garbage collector**.

Project 4 of the compilers course list, by **Mansour Abderezak** and **Badreddine Mamouni**
(4th year Informatique, cycle ingénieur, Université de Béjaïa).

*Status as of 24 November 2026: all seven milestones (M1 to M7) are finished.*

## What it is

We designed a small statically typed language called **Toy**. The compiler turns a Toy program into
bytecode, and a virtual machine written in C runs it. Memory is managed by a garbage collector that
is **precise**: it knows exactly which stack slots and heap fields are pointers, because the compiler
tells it (stack maps and type descriptors). It never guesses, and it never mistakes an integer for an
address. Two collectors are implemented, **Mark-and-Sweep** and **Stop-and-Copy** (Cheney).

```
prog.toy ──► [ compiler (Python) ] ──► prog.tbc ──► [ VM (C) + GC ] ──► output
              lexer → parser →                       loader → interpreter →
              type checker → code generator          heap → Mark-and-Sweep / Cheney
```

## Quick start

You need Python 3.10+, a C compiler (gcc or clang) and `make`.

```
make                 # build the virtual machine (vm/gcvm)
make test            # run every test
make demo            # guided demonstration
make bench           # compare the two collectors
```

Compile and run a program:

```
python3 compiler/toyc.py tests/list.toy -o list.tbc --dump     # --dump shows the bytecode
./vm/gcvm list.tbc --gc=copy --heap=1048576 --gc-stats
```

## The Toy language

```
struct Node { val: int; next: Node; }

fun push(head: Node, v: int): Node {
    var n: Node = new Node;
    n.val = v;
    n.next = head;
    return n;
}

fun main(): int {
    var list: Node = null;
    var i: int = 0;
    while (i < 1000000) {
        list = push(null, i);          // the old lists become garbage
        i = i + 1;
    }
    print(list.val);
    return 0;
}
```

- Types: `int` (64 bits, wraps around), `bool`, structs (references), arrays `T[]`, and `null`.
- Statements: `var`, assignment, `if` / `else if` / `else`, `while`, `return`, `print(...)`, calls.
- Expressions: `+ - * / %`, comparisons, `&&` `||` (lazy), `!`, `new T`, `new T[n]`, `a.field`, `a[i]`, calls.
- Every function returns a value; the program starts at `fun main(): int`, and the value it returns is the exit code.

The full rules are in `docs/specifications.tex`.

## The virtual machine

```
vm/gcvm <program.tbc> [--gc=ms|copy] [--heap=<bytes>] [--stress] [--verify] [--gc-stats]
```

| Option | Effect |
|---|---|
| `--gc=ms` (default) | Mark-and-Sweep: marks with an explicit stack (no recursion), sweeps into a free list that merges neighbouring blocks |
| `--gc=copy` | Stop-and-Copy (Cheney): two semi-spaces, forwarding pointers, roots updated in place |
| `--heap=<bytes>` | heap size, default 8 MB (with `copy` it is split into two semi-spaces) |
| `--stress` | collect before **every** allocation, and verify the heap after each collection |
| `--verify` | verify the heap after every collection |
| `--gc-stats` | print collector statistics on stderr at the end |

Exit codes: `0` to `99` the value returned by `main`; `1` bad command line; `100` runtime error
(division by zero, `null`, index out of bounds, negative array size, call depth > 10000);
`101` out of memory; `102` heap verifier error; `103` invalid `.tbc` file.

## Repository layout

```
compiler/
  toyc.py                the compiler command
  frontend/              from source text to a type-checked AST (M1, M2)
    lexer.py  parser.py  ast_nodes.py  toy_types.py  semantique.py  show_ast.py
  backend/               from the typed AST to the .tbc file (M3)
    codegen.py           code generator for one function, stack maps, type table
    program.py           the whole program: function table, relocation of jumps
    bytecode.py          instructions, stack maps, data structures
    tbc.py               writing and reading the .tbc file
    disassembler.py      the readable --dump
vm/                      the virtual machine (M4 to M7)
  main.c loader.c interp.c heap.c verify.c vm.h opcodes.h Makefile
tests/
  test_*.py              unit tests
  programs/              end-to-end test programs (.toy) with their expected output (.expected)
  bench/                 programs for the benchmark
  run_all.py  run_programs.py  benchmark.py
docs/                    cahier des charges, specifications (LaTeX), benchmark results
demo.sh  Makefile
```

## How the garbage collector knows what is a pointer

1. The type checker gives every expression and every variable a type; structs and arrays are references.
2. The code generator keeps a model of the operand stack while it emits code. At every `NEW`,
   `NEW_ARRAY` and `CALL` (the only places where the GC can run) it records a **stack map**: which
   local variables and which operand-stack slots hold references.
3. It also writes a **type descriptor** for each struct (which fields are references) and for each array type.
4. The collector starts from the slots marked in the stack maps of all active frames and follows
   only the fields marked in the descriptors.

The heap verifier checks all of this after a collection, including that the depth recorded in each
stack map is the number of values really on the stack, so a wrong stack map is caught at once.

## Tests

`make test` runs:

- **88 unit tests** (lexer, parser, type checker, code generator, program assembly, `.tbc` format,
  `toyc` command, and damaged `.tbc` files that the VM must refuse cleanly);
- **38 end-to-end programs**. Each one is compiled and run on both collectors with the heap verifier
  on, and, unless it is too big, again with `--stress`. The output must always be the one expected,
  computed independently in Python. They cover arithmetic, recursion, scoping, short-circuit
  evaluation, references, trees, cyclic structures, references that live only on the operand stack,
  arrays, runtime errors, out-of-memory, and compile errors with their line and column.

`make test-asan` does the same with AddressSanitizer and UndefinedBehaviorSanitizer.

## Benchmark

`python3 tests/benchmark.py` runs the programs of `tests/bench` with both collectors (full table in
`docs/benchmark.md`; the absolute numbers depend on the machine). Examples:

| program | heap | collector | collections | GC time (ms) | total (ms) |
|---|---|---|---|---|---|
| bench_garbage | 1 MB | Mark-and-Sweep | 91 | 9.3 | 140 |
| bench_garbage | 1 MB | Stop-and-Copy | 183 | 0.0 | 126 |
| bench_live | 4 MB | Mark-and-Sweep | 24 | 20.1 | 110 |
| bench_live | 4 MB | Stop-and-Copy | 128 | 66.8 | 156 |

When almost everything is garbage, Stop-and-Copy is cheaper: it only touches the live objects.
When a large set of objects stays alive, Mark-and-Sweep wins on a small heap, because Stop-and-Copy
has only half the heap to work with and copies the whole live set at every collection.

## Limits and choices

- Integer literals must fit in 32 bits (up to 2147483647); bigger values come from arithmetic.
- No strings, floats, `void`, inheritance, methods, generics or arrays of arrays.
- Limits: 64 locals per function, 64 fields per struct, 64 values on the stack at an allocation or a call, 10000 nested calls.
- The return analysis is conservative: a `return` that is only inside a `while` does not count.
- The VM checks that a `.tbc` file is consistent, but it trusts the compiler for the stack discipline
  of the bytecode (it is not a full bytecode verifier).
- Collectors: Mark-and-Sweep uses first fit; objects have a 16-byte header that also holds the block size.

## Still open

- Dates of the milestones and the supervisor's name (cahier des charges and specifications)
- Licence of the repository

## Requirements

- Python 3.10 or newer (the AST uses dataclasses with `kw_only`)
- A C11 compiler (gcc or clang) and `make`
