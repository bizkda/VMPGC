# VMPGC — Toy Compiler, Bytecode Virtual Machine & Precise Garbage Collectors

VMPGC is a small language implementation project. It contains:

- a **compiler written in Python** for the Toy language;
- a binary bytecode format (`.tbc`);
- a **virtual machine written in C** that loads and interprets that bytecode;
- a managed heap with two precise garbage collectors: **Mark-and-Sweep** and **Stop-and-Copy (Cheney)**;
- tests, benchmarks, a guided demo, and a browser-based garbage-collection visualizer.

The purpose of this README is to explain both the files and the ideas behind the implementation, then follow one program from the moment you type it until the CPU executes the VM.

---

## 1. The whole pipeline

When you write a Toy program, the CPU does not execute the Toy source directly. The Python compiler translates it into bytecode, and the C virtual machine interprets that bytecode.

```text
   You write source code
          |
          v
      prog.toy
          |
          v
  PYTHON COMPILER (compiler/)
  ┌───────────────────────────┐
  │ 1. Lexer                  │  characters -> tokens
  │ 2. Parser                 │  tokens -> AST
  │ 3. Type checker           │  AST -> checked AST
  │ 4. Code generator         │  checked AST -> bytecode
  │ 5. TBC writer             │  program -> binary file
  └───────────────────────────┘
          |
          v
       prog.tbc
          |
          v
  C VIRTUAL MACHINE (vm/)
  ┌───────────────────────────┐
  │ 6. Loader + validation    │  binary -> VM structures
  │ 7. Interpreter            │  fetch/decode/execute
  │ 8. Heap + garbage collect │  allocate and reclaim objects
  │ 9. Heap verifier          │  check heap consistency
  └───────────────────────────┘
          |
          v
  Native machine instructions of gcvm
          |
          v
        CPU runs
```

The VM is compiled from C to native machine code by the C compiler (GCC by default). The CPU executes those native instructions. The interpreter's C code decides what each Toy bytecode instruction means.

**Important distinction:** `PUSH_INT`, `ADD`, `CALL`, and `NEW` are instructions in your virtual machine's instruction set. They are not native CPU instructions. The CPU executes the C implementation of those instructions.

---

## 2. What language does the compiler implement?

The current Toy language supports:

- `int` and `bool`;
- `struct` declarations and struct references;
- arrays such as `int[]`, `bool[]`, and `Node[]`;
- `null`, `new`, variables, assignments and scopes;
- arithmetic, comparisons, boolean operators and short-circuit `&&` / `||`;
- `if`, `else`, `while`, function calls, `return`, and `print`.

A struct can contain both values and references. For example:

```toy
struct Node {
    value: int;
    next: Node;
}
```

This implementation has structs and functions, but it does **not** currently implement classes with methods, inheritance, `this`, or virtual dispatch. Those would be language extensions, not features to assume are already present.

---

## 3. Project files: what each part does

### 3.1 Root directory

| File | Responsibility |
|---|---|
| `Makefile` | Main project commands: build the VM, run tests, run sanitizers, launch the demo, run benchmarks, and clean generated files. |
| `README.md` | Project overview and usage documentation (this document). |
| `demo.sh` | A guided terminal demonstration: builds the VM, compiles a list program, compares collectors, exercises stress GC, and demonstrates errors. |
| `.gitignore` | Lists generated or local files Git should ignore. |
| `.vscode/settings.json` | Editor/workspace settings for VS Code; it does not participate in compilation or execution. |
| `web.txt` | Notes describing the web interface, how it is connected to the real compiler/VM, its checks, and its limitations. |

### 3.2 `compiler/` — the Python compiler

The compiler transforms source text into a `ProgramCode` object and then serializes it to `.tbc`.

#### Compiler entry point

| File | Responsibility |
|---|---|
| `compiler/toyc.py` | Command-line entry point. Reads a `.toy` file, calls the compilation pipeline, optionally prints readable bytecode with `--dump`, and writes the `.tbc` output. |
| `compiler/__init__.py` | Marks `compiler` as a Python package. |

#### `compiler/frontend/` — understanding the source language

| File | Responsibility |
|---|---|
| `compiler/frontend/lexer.py` | Lexer. Reads characters, recognizes keywords, identifiers, integer literals, operators and punctuation, and reports invalid characters with line/column positions. |
| `compiler/frontend/parser.py` | Parser. Consumes tokens and builds the Abstract Syntax Tree (AST). It implements the language grammar and expression precedence. |
| `compiler/frontend/ast_nodes.py` | Defines the AST node classes: expressions, statements, types, struct declarations, function declarations and complete programs. |
| `compiler/frontend/toy_types.py` | Defines the compiler's internal types (`IntType`, `BoolType`, `NullType`, `StructType`, `ArrayType`) and reference/type-compatibility helpers. |
| `compiler/frontend/checker.py` | Semantic/type checker. Checks declarations, names, scopes, expression types, function calls, assignments, returns, fields and arrays before code generation. |
| `compiler/frontend/show_ast.py` | Development/debugging utility that prints the AST as a tree. `--check` also runs the type checker. |
| `compiler/frontend/__init__.py` | Marks the frontend directory as a Python package. |

#### `compiler/backend/` — generating the VM program

| File | Responsibility |
|---|---|
| `compiler/backend/bytecode.py` | Defines the bytecode instruction list and numeric opcode mapping, instruction and function data structures, stack effects, safepoints, stack maps and GC type descriptors. |
| `compiler/backend/codegen.py` | Generates instructions for expressions, statements and functions. Manages local-variable slots, jump patching, type descriptors and stack maps. |
| `compiler/backend/program.py` | Connects the frontend and backend: parses, checks, generates each function, joins functions into one instruction array, and adjusts jump/stack-map positions to global instruction indexes. |
| `compiler/backend/tbc.py` | Serializes a `ProgramCode` into the binary `.tbc` format and reads it back. It checks the `TBC1` magic value, layout, truncation and trailing bytes. |
| `compiler/backend/disassembler.py` | Converts a compiled program into readable text for `toyc.py --dump`, including function boundaries, type descriptors and stack-map details. |
| `compiler/backend/__init__.py` | Marks the backend directory as a Python package. |

### 3.3 `vm/` — the C virtual machine

The VM loads `.tbc` files, executes bytecode, manages the heap, and checks heap consistency.

| File | Responsibility |
|---|---|
| `vm/main.c` | Program entry point. Parses CLI options, loads the bytecode, initializes the heap and value stack, runs the interpreter, prints optional GC statistics, and frees resources. |
| `vm/vm.h` | Shared VM definitions: values, instructions, functions, type information, stack maps, call frames, heap state, limits, exit codes and function declarations. |
| `vm/opcodes.h` | C numeric opcode definitions. The order must match `OPCODE_LIST` in `compiler/backend/bytecode.py`. |
| `vm/loader.c` | Reads the binary `.tbc` file, builds the VM's program structures, and validates indexes, functions, jumps, types, instructions and stack maps before execution. |
| `vm/interp.c` | Bytecode interpreter. Fetches an instruction using the program counter (`pc`), executes its behavior, manipulates the value stack, creates call frames, and requests heap allocations. |
| `vm/heap.c` | Heap allocator and both garbage collectors. Finds roots using stack maps, follows references using type descriptors, allocates objects, reclaims memory and records GC statistics. |
| `vm/verify.c` | Heap verifier. Checks heap structure and object/reference consistency when verification is enabled. |
| `vm/Makefile` | Builds `gcvm`; its `debug` target builds an AddressSanitizer/UndefinedBehaviorSanitizer version. |

The generated executable `vm/gcvm` is a build artifact, not a C source file. It can be recreated with `make`.

### 3.4 `tests/` — checking correctness

| File or directory | Responsibility |
|---|---|
| `tests/run_all.py` | Builds the VM, runs all `test_*.py` unit-test scripts, then runs the end-to-end Toy programs. Supports `--asan`. |
| `tests/run_programs.py` | Compiles each `.toy` test program, runs it with both collectors, enables the verifier, optionally runs stress mode, and compares output and exit codes with expected results. |
| `tests/test_lexer.py` | Tests lexical analysis. |
| `tests/test_parser.py` | Tests parsing and AST construction. |
| `tests/test_checker.py` | Tests semantic and type checking. |
| `tests/test_codegen.py` | Tests generated instructions, control flow, local slots, structs, arrays and stack maps. |
| `tests/test_program.py` | Tests assembly of generated functions into a complete program. |
| `tests/test_tbc.py` | Tests binary serialization/deserialization, format layout, malformed files and consistency between Python and C opcode numbering. |
| `tests/test_toyc.py` | Tests the compiler command-line interface. |
| `tests/test_vm_files.py` | Tests how the VM handles bytecode files, including invalid files. |
| `tests/programs/*.toy` | End-to-end source programs covering arithmetic, loops, recursion, structs, arrays, references, cycles, stress cases and expected runtime/compiler errors. |
| `tests/programs/*.expected` | Expected standard output for the corresponding end-to-end program. |
| `tests/list.toy` | Larger list/garbage-collection example used by the demo. |
| `tests/list.toy` and `tests/arrays.toy` | Additional standalone source examples used by tests. |
| `tests/benchmark.py` | Runs the collector benchmarks and can write a Markdown report. |
| `tests/bench/*.toy` | Benchmark workloads: mostly garbage, a large live set, and a tree-shaped live structure. |

The end-to-end runner reads optional comments at the top of a test program, such as `@heap`, `@exit`, `@expect-gc`, `@stress-heap`, `@no-stress`, and `@compile-error`. These control the test configuration and expected result.

### 3.5 `docs/` — specifications and results

| File | Responsibility |
|---|---|
| `docs/cahier_des_charges.tex` | LaTeX source of the project requirements/specification document. |
| `docs/specifications.tex` | LaTeX source of the technical specifications, including the language, bytecode and VM design. |
| `docs/cahier_des_charges_apercu.pdf` | PDF preview of the requirements document. |
| `docs/specifications_apercu.pdf` | PDF preview of the technical specifications. |
| `docs/benchmark.md` | Recorded comparison of Mark-and-Sweep and Stop-and-Copy on the benchmark programs and heap sizes. |

### 3.6 `web/` — interactive visualizer

| File | Responsibility |
|---|---|
| `web/index.html` | Browser interface: Toy editor, example selector, collector and heap-size controls, output/bytecode tabs, and animated heap visualization. |
| `web/server.py` | Local HTTP server. It invokes the real Python compiler and real C VM, returns output and bytecode, and supplies program metadata to the browser. |
| `web/gcsim.js` | JavaScript simulator used to create visualization events and animate heap/GC states in the browser. It is for visualization; the actual program result comes from the real VM. |

The web interface lets you select Mark-and-Sweep or Stop-and-Copy, choose a heap size, compile and run a program, inspect its bytecode/output, and step through the visualized collection events.

---

## 4. Important theory behind the project

### 4.1 Lexer: characters become tokens

The lexer does not understand the meaning of a complete program. Its job is to group characters into meaningful units called **tokens**.

For example:

```toy
print(2 + 3 * 4);
```

becomes approximately:

```text
KEYWORD(print)
(
INTEGER(2)
OPERATOR(+)
INTEGER(3)
OPERATOR(*)
INTEGER(4)
)
;
EOF
```

Whitespace and comments are skipped. Tokens keep line and column information so errors can point to the source location.

### 4.2 Parser: tokens become an AST

The parser checks whether the token sequence follows the grammar and constructs an **Abstract Syntax Tree**.

For the expression `2 + 3 * 4`, the AST is:

```text
       +
      / \
     2   *
        / \
       3   4
```

Multiplication is lower in the tree than the addition's right operand because `*` has higher precedence. The AST captures structure; it is not yet bytecode.

### 4.3 Type checker: is the program meaningful?

A syntactically valid program can still be invalid semantically. For example, adding an integer to a boolean should be rejected.

The checker verifies rules such as:

- arithmetic operators receive integer operands;
- conditions are boolean;
- variables and functions exist;
- function arguments match parameter types;
- returned values match the function's declared return type;
- struct fields and array element types are valid;
- `null` is used only where a reference type is expected.

The compiler should stop here if the program is invalid. Code generation should not need to guess what the programmer meant.

### 4.4 Code generation: AST becomes stack bytecode

The backend emits instructions for a **stack-based virtual machine**.

A stack machine evaluates expressions by pushing values onto an operand stack and letting instructions consume them.

For example:

```text
PUSH_INT 2
PUSH_INT 3
PUSH_INT 4
MUL
ADD
```

Stack evolution:

```text
PUSH_INT 2       [2]
PUSH_INT 3       [2, 3]
PUSH_INT 4       [2, 3, 4]
MUL              [2, 12]     (3 * 4)
ADD              [14]        (2 + 12)
```

`MUL` consumes the top two values and pushes their product. `ADD` does the same with addition. This is why the compiler emits the operands before the operator.

The `Instruction` structure stores an opcode and an integer operand. Some instructions need an operand (for example, `PUSH_INT 42`, `LOAD_LOCAL 0`, `JMP 12`, `CALL 1`, `NEW 1`); others do not.

The numeric opcode identifies the operation. The operand supplies the operation's parameter. The readable mnemonic is for humans and debugging.

### 4.5 Functions, locals and call frames

Each function has:

- a start position in the global instruction array;
- a parameter count;
- a local-variable count.

Local variables occupy numbered slots. A function call creates a **frame**. The arguments become the first local slots of the callee; the remaining local slots are initialized. The operand stack for that frame follows its locals in the VM's value stack.

The interpreter uses the program counter (`pc`) to know which instruction to execute next. `JMP` changes the `pc`; `JZ` pops a condition and jumps if it is zero. `CALL` creates a new frame, and `RET` removes the callee frame and returns its result to the caller.

### 4.6 Bytecode file: `.tbc`

The Python compiler does not pass Python objects directly to the C VM. It writes a portable binary representation.

The file starts with the four-byte magic value:

```text
TBC1
```

The format then stores, in little-endian order:

1. the type table;
2. the function table and the index of `main`;
3. the instruction count and instructions;
4. the stack-map count and stack maps.

Each instruction occupies **8 bytes**:

```text
1 byte opcode | 3 bytes padding | 4 byte signed operand
```

Each stack map stores:

```text
pc | depth | locals_mask | stack_mask
```

The type table and stack maps are important to garbage collection; they are not just debugging metadata.

### 4.7 Loader: validate before execution

The C loader reads the `.tbc` file and constructs the VM's in-memory program representation.

It checks that the file is structurally valid and that referenced entities exist: function indexes, local slots, jump targets, type IDs, opcode values and stack maps. A malformed file should be rejected rather than interpreted as if it were valid bytecode.

### 4.8 Interpreter: fetch, decode, execute

The interpreter repeatedly:

1. reads the instruction at `code[pc]`;
2. examines its opcode;
3. performs the operation;
4. updates the stack, locals, frame or `pc`.

For example, `ADD` combines the top two stack values. `GETFIELD` reads a field from a struct object. `NEW` asks the heap allocator for a new object. `PRINT_INT` pops an integer and prints it.

This is the **fetch–decode–execute cycle** implemented in C.

### 4.9 Stack versus heap

The VM uses two different memory areas for different purposes:

- **Value stack:** temporary values, local variables, function arguments and call frames.
- **Heap:** dynamically allocated structs and arrays that can outlive the instruction that created them.

A local variable can contain a reference to an object on the heap. Several variables can refer to the same object. Objects can also refer to other objects.

When an object is no longer reachable from the program's live references, its memory can be reclaimed.

### 4.10 Garbage collection: reachability

Garbage collection answers this question:

> Starting from the program's roots, which heap objects can still be reached?

The VM's roots are reference-valued local slots and operand-stack slots in active call frames. From those roots, the collector follows references inside objects.

An object that cannot be reached from any root is garbage.

#### Precise garbage collection

A conservative collector might treat a value that merely looks like an address as a pointer. VMPGC instead uses metadata to know exactly which slots contain references.

It uses two kinds of metadata:

**A. Stack maps**

A stack map is associated with each allocation or call safepoint: `NEW`, `NEW_ARRAY`, and `CALL`.

It records:

- `pc`: instruction index of the safepoint;
- `depth`: number of operand-stack values represented by the map;
- `locals_mask`: one bit per local slot;
- `stack_mask`: one bit per operand-stack slot.

A bit set to `1` means that slot contains a reference. A bit set to `0` means it is not a reference. Bit 0 of `stack_mask` describes the bottom/first slot of the mapped operand stack.

The compiler records the stack-map depth after the relevant instruction operands have been popped. For example, `NEW_ARRAY` removes the array size before allocating. At a `CALL` safepoint, the call arguments have been transferred out of the caller's operand stack into the callee's local slots. The suspended caller and the active callee each have a frame/map position that lets the collector find their roots.

**B. Type descriptors**

A type descriptor describes the layout of heap objects:

- struct: field count and a pointer mask indicating which fields are references;
- array of values: elements are not references;
- array of references: every element is a reference.

For a struct `Node { value: int; next: Node; }`, the pointer mask is `0b10`: field 0 is an integer, field 1 is a reference.

This is why an integer that happens to have the same numeric value as an address is not followed by the collector.

### 4.11 The two collectors

#### Mark-and-Sweep (`--gc=ms`)

1. **Mark:** begin at roots and mark every reachable object, following only reference fields.
2. **Sweep:** scan the heap. Keep marked objects and turn unmarked objects into free blocks. Adjacent free blocks are merged.

Advantages:
- does not move live objects;
- can use the whole heap for allocation.

Trade-offs:
- must scan the heap during sweeping;
- can leave free space fragmented.

#### Stop-and-Copy / Cheney (`--gc=copy`)

The heap is divided into two equal semi-spaces:

- from-space: where objects currently live;
- to-space: where live objects will be copied.

During collection:

1. copy objects referenced by roots into to-space and update those roots;
2. scan the copied objects in order;
3. copy any referenced objects not copied yet, updating references;
4. when scanning reaches the end of copied objects, all reachable objects have been copied;
5. switch the roles of the two spaces.

The forwarding information prevents the same object from being copied more than once.

Advantages:
- allocation is fast and sequential;
- live objects become compacted.

Trade-offs:
- only one semi-space is available for allocations at a time;
- collection copies all live objects.

#### Why have two collectors?

Their performance depends on the workload. When most allocated objects quickly become garbage, copying can be efficient because it copies only survivors. When many objects remain alive, copying them can be expensive; Mark-and-Sweep may be better. The benchmark results in `docs/benchmark.md` illustrate that the winner depends on the program and heap size.

### 4.12 Heap verifier and stress mode

`--verify` asks the VM to verify the heap after collections. `--stress` forces a collection before every allocation and also enables verification.

Stress mode is useful because it makes bugs in root tracking easier to expose. For example, if an object exists only temporarily on the operand stack while another object is being allocated, the stack map must keep that first object alive.

---

## 5. One complete example: from typing Toy to CPU execution

We will use a small program that creates a linked-list node, calculates a value, stores it in the node, and prints it.

### 5.1 The source code you type

```toy
struct Node {
    value: int;
    next: Node;
}

fun make(head: Node, value: int): Node {
    var n: Node = new Node;
    n.value = value;
    n.next = head;
    return n;
}

fun main(): int {
    var head: Node = null;
    head = make(head, 2 + 3 * 4);
    print(head.value);
    return 0;
}
```

The intended result is `14`.

### 5.2 Step 1 — the lexer

The lexer reads the source character by character and creates tokens. A fragment from the function call expression becomes:

```text
IDENTIFIER(make)
(
IDENTIFIER(head)
,
INTEGER(2)
+
INTEGER(3)
*
INTEGER(4)
)
```

The lexer recognizes `fun`, `struct`, `new`, `int`, and `return` as keywords. It does not decide whether `head` is a valid variable; that is a later stage.

### 5.3 Step 2 — the parser and AST

The parser recognizes declarations, statements and expressions and builds the AST.

The expression `2 + 3 * 4` is represented as:

```text
       +
      / \
     2   *
        / \
       3   4
```

The function call is a `Call` expression, `head.value` is a `FieldAccess`, and `new Node` is a `NewObject` expression. These correspond to AST classes in `ast_nodes.py`.

### 5.4 Step 3 — type checking

The checker resolves the declared struct and functions.

- `head` has type `Node`.
- `value` has type `int`.
- `n` has type `Node`.
- `n.value` is an integer field.
- `n.next` is a `Node` reference field.
- `make` accepts `(Node, int)` and returns `Node`.
- `2 + 3 * 4` has type `int`.
- `print(head.value)` prints an integer.

The checker also knows that `Node` is a reference type. That information is later used by code generation to create the GC metadata.

### 5.5 Step 4 — code generation

The compiler generates bytecode. The actual dump for this example is:

```text
== types ==
  1  Node  (struct, 2 fields, pointer mask 0b10)

== functions ==
  0  make  start=0 parameters=2 locals=3
  1  main  start=10 parameters=0 locals=1  <- entry point

== code ==
function make
   0  NEW          1
   1  STORE_LOCAL  2
   2  LOAD_LOCAL   2
   3  LOAD_LOCAL   1
   4  PUTFIELD     0
   5  LOAD_LOCAL   2
   6  LOAD_LOCAL   0
   7  PUTFIELD     1
   8  LOAD_LOCAL   2
   9  RET

function main
  10  PUSH_NULL
  11  STORE_LOCAL  0
  12  LOAD_LOCAL   0
  13  PUSH_INT     2
  14  PUSH_INT     3
  15  PUSH_INT     4
  16  MUL
  17  ADD
  18  CALL         0
  19  STORE_LOCAL  0
  20  LOAD_LOCAL   0
  21  GETFIELD     0
  22  PRINT_INT
  23  PUSH_INT     0
  24  RET
```

The important instructions are:

| Instruction | Meaning |
|---|---|
| `NEW 1` | Allocate a struct whose type ID is 1 (`Node`). |
| `STORE_LOCAL 2` | Store the new reference in local slot 2 (`n`) of `make`. |
| `PUTFIELD 0` | Store a value in field 0 (`value`). |
| `PUTFIELD 1` | Store a reference in field 1 (`next`). |
| `CALL 0` | Call function index 0 (`make`). |
| `GETFIELD 0` | Read field 0 from the node. |
| `PRINT_INT` | Pop and print the integer. |

Notice that `MUL` occurs before `ADD`. The bytecode preserves the precedence represented by the AST.

### 5.6 Step 5 — stack execution of the arithmetic

Inside `main`, the arithmetic instructions are:

```text
PUSH_INT 2
PUSH_INT 3
PUSH_INT 4
MUL
ADD
```

The operand stack evolves as follows:

| Instruction | Stack after instruction |
|---|---|
| `PUSH_INT 2` | `[2]` |
| `PUSH_INT 3` | `[2, 3]` |
| `PUSH_INT 4` | `[2, 3, 4]` |
| `MUL` | `[2, 12]` |
| `ADD` | `[14]` |

Then `CALL 0` passes the `head` reference and integer `14` as the two arguments to `make`.

### 5.7 Step 6 — what happens during `CALL` and `NEW`?

`CALL 0` creates a frame for `make`.

The arguments become its first two local slots:

```text
make locals:
slot 0 -> head   (Node reference)
slot 1 -> value  (int)
slot 2 -> n      (Node reference, initially null/zero)
```

When `make` executes `NEW 1`, the interpreter calls the heap allocator. This is a **safepoint**: garbage collection may run there.

The compiler has emitted this stack map for `make`:

```text
locals_mask = 0b101
stack_mask  = 0
depth       = 0
```

Read `0b101` from right to left by slot number:

```text
slot 2: 1 -> reference (n)
slot 1: 0 -> integer   (value)
slot 0: 1 -> reference (head)
```

The collector therefore knows which local slots are references. It does not treat the integer `value` as an object pointer.

The type descriptor for `Node` is:

```text
field 0: value -> int
field 1: next  -> Node reference

pointer_mask = 0b10
```

When the collector scans a `Node`, it follows field 1 but does not follow field 0.

### 5.8 Step 7 — the heap object

`NEW 1` allocates a heap block for a `Node`. The VM's object layout has a 16-byte header followed by 8-byte slots.

Conceptually, after the assignments:

```text
n
|
v
+----------------------+
| Node object          |
+----------------------+
| value = 14           |
| next  = null         |
+----------------------+
```

`PUTFIELD 0` writes `14` to the first field. `PUTFIELD 1` writes `head` to the second field. In this particular run, `head` was initially `null`.

`make` returns the reference. The caller stores it in its `head` local.

### 5.9 Step 8 — loading the `.tbc` file

Before execution, `main.c` calls the loader.

The loader reads the `TBC1` file and reconstructs:

- type descriptors;
- function metadata;
- instructions;
- stack maps;
- the index of `main`.

It validates the file before the interpreter runs. For example, a jump must stay inside its function, a local slot must exist, and every allocation/call safepoint must have a stack map.

### 5.10 Step 9 — the C interpreter executes the bytecode

The interpreter starts at the `main` function's first instruction. It fetches `code[pc]`, dispatches on the opcode, performs the operation and updates `pc`.

For this program:

1. `PUSH_NULL` pushes the initial null reference.
2. `STORE_LOCAL 0` initializes `head`.
3. arithmetic instructions calculate `14`;
4. `CALL 0` enters `make`;
5. `NEW 1` allocates a `Node`;
6. field instructions initialize it;
7. `RET` returns the reference to `main`;
8. `GETFIELD 0` reads `14`;
9. `PRINT_INT` prints `14`;
10. `RET` returns `0` from `main`, ending the program.

### 5.11 Step 10 — what the CPU actually runs

The C files (`main.c`, `loader.c`, `interp.c`, `heap.c`, and `verify.c`) are compiled into the native executable `vm/gcvm`.

At runtime, the CPU executes native instructions from that executable. Those native instructions implement the interpreter's switch/case logic, stack manipulation, memory accesses, calls, and garbage collector.

The CPU is not directly executing the text `PUSH_INT 2` or `MUL`. Instead:

```text
Toy source
   |
   v
Python compiler
   |
   v
.tbc bytecode
   |
   v
C interpreter running as native machine code
   |
   v
CPU executes the C VM's machine instructions
```

The final visible output is:

```text
14
```

---

## 6. How to build and run the project

Run commands from the project root.

### Build the C virtual machine

```bash
make
```

This builds `vm/gcvm`.

### Compile a Toy program

```bash
python3 compiler/toyc.py tests/programs/arith.toy -o arith.tbc
```

### Compile and display readable bytecode

```bash
python3 compiler/toyc.py tests/programs/arith.toy --dump
```

### Run with Mark-and-Sweep

```bash
./vm/gcvm arith.tbc --gc=ms --gc-stats
```

### Run with Stop-and-Copy

```bash
./vm/gcvm arith.tbc --gc=copy --gc-stats
```

### Use a small heap and verify it

```bash
./vm/gcvm arith.tbc --gc=ms --heap=4096 --verify --gc-stats
```

### Stress mode

```bash
./vm/gcvm arith.tbc --gc=copy --heap=65536 --stress --gc-stats
```

Stress mode collects before every allocation and enables heap verification.

### Show the AST

```bash
python3 compiler/frontend/show_ast.py tests/list.toy
python3 compiler/frontend/show_ast.py tests/list.toy --check
```

### Run the tests

```bash
make test
```

### Run tests with AddressSanitizer and UndefinedBehaviorSanitizer

```bash
make test-asan
```

### Run the guided demo

```bash
make demo
```

### Run the benchmarks

```bash
make bench
```

The benchmark report is written to `docs/benchmark.md`.

### Launch the browser visualizer

```bash
python3 web/server.py
```

Then open the local address printed by the server (by default `http://localhost:8005`). Select a Toy example or type your own, choose a collector and heap size, and click **Compiler et exécuter**.

The real compiler and real C VM produce the program result. `gcsim.js` supplies the animated heap visualization.

---

## 7. Useful mental model

When debugging or explaining VMPGC, keep these responsibilities separate:

| Component | Main question it answers |
|---|---|
| Lexer | What are the tokens in the source text? |
| Parser | Do the tokens form a valid program, and what is its AST? |
| Type checker | Does the program obey the language's type and semantic rules? |
| Code generator | Which VM instructions implement this checked AST? |
| TBC writer | How do we store the program in a binary file? |
| Loader | Is the bytecode file valid, and how do we reconstruct it? |
| Interpreter | What does the next bytecode instruction do? |
| Heap allocator | Where can a new object be placed? |
| Garbage collector | Which objects are still reachable, and which can be reclaimed? |
| Stack maps | Which local and operand-stack slots are references at a safepoint? |
| Type descriptors | Which fields/elements inside an object are references? |
| Heap verifier | Is the heap still structurally consistent? |
| CPU | Which native machine instructions execute the compiled C VM? |

The key idea of the project is that **the compiler and VM cooperate**: the compiler does not only generate executable bytecode. It also generates the stack maps and type descriptors that allow the C VM to perform precise garbage collection safely.
