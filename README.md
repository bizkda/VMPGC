# VMPGC

A compiler (Python) and a bytecode virtual machine (C) with a **precise garbage collector**.

Project 4 of the compilers course list, by **Mansour Abderezak** and **Badreddine Mamouni**
(4th year Informatique, cycle ingénieur, Université de Béjaïa).

*Status as of 14 November 2026: M1 (parser) and M2 (type checker) are finished. Next: M3, the code generator.*

## What it is

We design a small statically typed language called **Toy**. The compiler turns Toy programs into
bytecode, and a VM written in C runs that bytecode. Memory is managed by a garbage collector that is
**precise**: it knows exactly which stack slots and heap fields are pointers, because the compiler
tells it (stack maps and type descriptors). It never guesses.

```
list.toy ──► [ compiler (Python) ] ──► list.tbc ──► [ VM (C) + GC ] ──► output
              lexer → parser →                       loader → interpreter →
              type checker → codegen                 heap → Mark-and-Sweep / Cheney
              └── done ──────┘ └ to do ┘              └──────────── to do ───────────┘
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
compiler/
  lexer.py        text -> tokens
  ast_nodes.py    the classes of the syntax tree
  parser.py       tokens -> AST
  toy_types.py    the types: int, bool, null, struct, array
  checker.py      type checker (semantic analysis)
  show_ast.py     prints the AST as a tree (--check adds the types)
vm/               loader, interpreter, heap, garbage collectors   (C, from M4)
tests/            .toy programs and unit tests
docs/             cahier des charges and specifications (LaTeX)
```

## Documents

- **Cahier des charges** (`docs/cahier_des_charges.tex`): the need, scope, objectives, risks, planning.
- **Spécifications** (`docs/specifications.tex`): the Toy language, typing rules, bytecode instruction
  set, `.tbc` file format, stack maps, VM options and GC algorithms.

## Try it

```
python3 tests/test_parser.py                           # parser tests
python3 tests/test_checker.py                          # type checker tests
python3 compiler/show_ast.py tests/list.toy            # the AST as a tree
python3 compiler/show_ast.py tests/list.toy --check    # the same tree, with the type of every node
```

An error gives the exact position:

```
bad.toy:2:18: type mismatch: expected int, found bool
```

## Where we are

### M1, lexer, AST and parser: done

- [x] Repository, `.gitignore`, README
- [x] Cahier des charges (LaTeX)
- [x] Specifications (LaTeX)
- [x] **Lexer** (`compiler/lexer.py`): tokens with line and column, `//` comments, two-character
      operators, clear errors
- [x] **AST** (`compiler/ast_nodes.py`): base classes `Statement` and `Expression`, all node types
- [x] **Parser** (`compiler/parser.py`):
  - [x] token helpers (`current_token`, `look_ahead`, `consume_token`, `is_operator`, `is_keyword`,
        `match_operator`, `expect_*`, `error`)
  - [x] types, `struct`, `fun` with its parameter list, `parse_program`
  - [x] statements: `var`, assignment, `if` / `else if` / `else`, `while`, `return`, `print`, blocks, call statements
  - [x] expressions: operator precedence, unary operators, calls, `.field`, `[index]`, `new T`, `new T[n]`
- [x] Parser tests (valid programs, plus invalid ones that give a precise error)

### M2, type checker: done

- [x] Types as objects (`compiler/toy_types.py`): `int`, `bool`, `null`, struct, array; compatibility rules
- [x] Collect struct and function declarations (order does not matter, structs may refer to each other)
- [x] Check `main(): int` exists
- [x] Scopes for variables, no masking
- [x] Type of every expression, stored in `static_type`; type of every variable and parameter,
      stored in `resolved_type` (what the code generator will read)
- [x] Check each statement and expression against the typing rules T1 to T16 of the specifications
- [x] Check that every function returns on every path
- [x] Tests for each error message (with line and column)

Rules of the checker worth knowing:
- `return;` without a value is refused: Toy has no `void` type.
- Only a call can be used as a statement (`1 + 2;` is an error).
- `var x: int = x;` is an error: the value is checked before the variable exists.
- The return analysis is conservative: a `return` that is only inside a `while` does not count,
  because the loop might never run. Put a `return` after the loop.
- Arrays of arrays are not supported.

## What remains

| Milestone | Goal | Done when | Status |
|---|---|---|---|
| **M1** Lexer, AST, parser | source text to AST | all example programs parse; syntax errors are located | done |
| **M2** Type checker | check types, resolve names | ill-typed programs are rejected; every expression has a type | done |
| **M3** Code generator | AST to bytecode, type descriptors, stack maps | `.tbc` file written; readable disassembly (`--dump`) | **next** |
| **M4** VM without GC | loader, interpreter, plain heap | output tests pass | to do |
| **M5** Mark-and-Sweep | precise GC driven by stack maps | `list.toy` runs in a bounded heap | to do |
| **M6** Stop-and-Copy | Cheney's algorithm, two semi-spaces | same outputs as M5 | to do |
| **M7** Stress and measures | collect on every allocation, heap verifier, benchmarks | zero verifier errors; comparison report | to do |

Priority: **M1 to M5** already satisfy the project statement (it asks for Stop-and-Copy *or*
Mark-and-Sweep). M6 and M7 make the result stronger.

### Detail of the later milestones

**M3, code generator** (reads the typed AST from M2)
- [ ] Assign one local slot per variable declaration (parameters first)
- [ ] Generate instructions for statements and expressions (`JZ` and `JMP` for `if`, `while`, `&&`, `||`)
- [ ] Build the type descriptor table (which struct fields are pointers)
- [ ] Track the types of the operand stack to produce a stack map at every `NEW`, `NEW_ARRAY` and `CALL`
- [ ] Write the `.tbc` file; write the disassembler
- [ ] Command line: `python3 compiler/toyc.py prog.toy [-o prog.tbc] [--dump]`
- [ ] Tests: expected bytecode for small programs

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

## Decisions

Settled:
- Toy has no `void` type: every function returns a value (implemented in the checker).

Still open:
- Dates of the milestones and the supervisor's name (cahier des charges and specifications)
- Heap size default (8 MB proposed) and object header size (16 bytes proposed, confirm at M4)
- Final instruction list (confirm at M3); `PRINT` is split into `PRINT_INT` and `PRINT_BOOL`
- Licence of the repository

## Requirements

- Python 3.10 or newer (the AST uses dataclasses with `kw_only`)
- A C11 compiler (gcc or clang) and `make`, from M4 on