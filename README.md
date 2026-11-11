# VMPGC

A compiler (Python) and a bytecode virtual machine (C) with a **precise garbage collector**.

Project 4 of the compilers course list, by **Mansour Abderezak** and **Badreddine Mamouni**
(4th year Informatique, cycle ingénieur, Université de Béjaïa).

*Status as of 10 November 2026.*

## What it is

We design a small statically typed language called **Toy**. The compiler turns Toy programs into
bytecode, and a VM written in C runs that bytecode. Memory is managed by a garbage collector that is
**precise**: it knows exactly which stack slots and heap fields are pointers, because the compiler
tells it (stack maps and type descriptors). It never guesses.

```
list.toy ──► [ compiler (Python) ] ──► list.tbc ──► [ VM (C) + GC ] ──► output
              lexer → parser →                       loader → interpreter →
              type checker → codegen                 heap → Mark-and-Sweep / Cheney
```

Example Toy program (`tests/list.toy`): it allocates a million nodes and almost all of them become
garbage, so it only runs in a bounded heap if the GC works.

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
        list = push(null, i);
        i = i + 1;
    }
    print(list.val);
    return 0;
}
```

## Repository layout

```
compiler/   lexer, AST, parser, type checker, code generator   (Python)
vm/         loader, interpreter, heap, garbage collectors      (C)
tests/      .toy programs, expected outputs, unit tests
docs/       cahier des charges and specifications (LaTeX)
```

## Documents

- **Cahier des charges** (`docs/cahier_des_charges.tex`): the need, scope, objectives, risks, planning.
- **Spécifications** (`docs/specifications.tex`): the Toy language, typing rules, bytecode instruction
  set, `.tbc` file format, stack maps, VM options and GC algorithms.

## Where we are

### Done

- [x] Repository, `.gitignore`, README
- [x] Cahier des charges (LaTeX)
- [x] Specifications (LaTeX)
- [x] **Lexer** (`compiler/lexer.py`): tokens with line and column, `//` comments, two-character
      operators, clear errors
- [x] **AST** (`compiler/ast_nodes.py`): base classes `Statement` and `Expression`, all node types
- [x] **Parser, part 1** (`compiler/parser.py`): token helpers (`current_token`, `look_ahead`,
      `consume_token`, `is_operator`, `is_keyword`, `match_operator`, `expect_*`, `error`) and
      `parse_type`

### In progress: M1, parser

- [ ] `parse_struct`  ← **next**
- [ ] `parse_function` and its parameter list
- [ ] `parse_program` (loop over all declarations until end of file)
- [ ] Statements: `var`, assignment, `if` / `else`, `while`, `return`, `print`, blocks, call statements
- [ ] Expressions: operator precedence, unary operators, calls, `.field`, `[index]`, `new T`, `new T[n]`
- [ ] Parser tests (valid programs, plus invalid ones that must give a precise error)

**M1 is finished when** `tests/list.toy` and `tests/arrays.toy` parse completely and the invalid
programs give errors with the right line and column.

## What remains

| Milestone | Goal | Done when |
|---|---|---|
| **M1** Lexer, AST, parser | source text to AST | all example programs parse; syntax errors are located |
| **M2** Type checker | check types, resolve names | ill-typed programs are rejected; every expression knows if it is a reference |
| **M3** Code generator | AST to bytecode, type descriptors, stack maps | `.tbc` file written; readable disassembly (`--dump`) |
| **M4** VM without GC | loader, interpreter, plain heap | output tests pass |
| **M5** Mark-and-Sweep | precise GC driven by stack maps | `list.toy` runs in a bounded heap |
| **M6** Stop-and-Copy | Cheney's algorithm, two semi-spaces | same outputs as M5 |
| **M7** Stress and measures | collect on every allocation, heap verifier, benchmarks | zero verifier errors; comparison report |

Priority: **M1 to M5** already satisfy the project statement (it asks for Stop-and-Copy *or*
Mark-and-Sweep). M6 and M7 make the result stronger.

### Detail of the later milestones

**M2, type checker**
- [ ] Collect struct and function declarations (order does not matter)
- [ ] Check each statement and expression against the typing rules T1 to T16 of the specifications
- [ ] Check that every function returns on every path and that `main(): int` exists
- [ ] Annotate each expression with its type and whether it is a reference
- [ ] Tests for each error message

**M3, code generator**
- [ ] Assign one local slot per variable declaration
- [ ] Generate instructions for statements and expressions (`JZ` and `JMP` for `if`, `while`, `&&`, `||`)
- [ ] Build the type descriptor table (which struct fields are pointers)
- [ ] Simulate the operand stack types to produce a stack map at every `NEW`, `NEW_ARRAY` and `CALL`
- [ ] Write the `.tbc` file; write the disassembler
- [ ] Command line: `python3 compiler/toyc.py prog.toy [-o prog.tbc] [--dump]`

**M4, VM without GC**
- [ ] Load and validate a `.tbc` file
- [ ] Interpreter loop, call frames, value stack
- [ ] Runtime errors with clear messages (division by zero, `null`, bounds, depth)
- [ ] Heap with plain allocation; object header and layout as in the specifications
- [ ] Command line: `vm/gcvm prog.tbc`

**M5, Mark-and-Sweep**
- [ ] Find roots from the stack maps of every active frame
- [ ] Mark with an explicit stack (no recursion: a list of one million nodes must not overflow the C stack)
- [ ] Sweep with a free list that merges neighbouring free blocks
- [ ] `--heap=<bytes>` and `--gc-stats`

**M6, Stop-and-Copy**
- [ ] Two semi-spaces, bump-pointer allocation
- [ ] Cheney's scan with forwarding pointers; update all roots
- [ ] `--gc=ms|copy`

**M7, stress and measures**
- [ ] `--stress` (collect before every allocation) and the heap verifier (`--verify`)
- [ ] Test programs: lists, trees, cyclic structures
- [ ] Run everything under AddressSanitizer and UBSan
- [ ] Benchmark both collectors and write the comparison

## Decisions still open

- Dates of the milestones and the supervisor's name (cahier des charges and specifications)
- Heap size default (8 MB proposed) and object header size (16 bytes proposed, confirm at M4)
- Final instruction list (confirm at M3); `PRINT` is split into `PRINT_INT` and `PRINT_BOOL`
- No `void` type in Toy: every function returns a value (to confirm)
- Licence of the repository

## Running the tests

```
python3 tests/test_lexer.py
python3 tests/test_parser.py
```

*(Compiler and VM command lines are listed above under M3 and M4 and do not exist yet.)*

## Requirements

- Python 3.10 or newer (the AST uses dataclasses with `kw_only`)
- A C11 compiler (gcc or clang) and `make`, from M4 on