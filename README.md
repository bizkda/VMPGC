# VMPGC

Toy compiler (Python) + bytecode VM (C) with a **precise** garbage collector.

```
compiler/   lexer, parser, type checker, codegen   (Python)
vm/         loader, interpreter, heap, GC          (C)
tests/      .toy programs + tests
```

## Status
- [x] M1 lexer + parser
- [ ] M2 type checker
- [ ] M3 codegen + type descriptors + stack maps
- [ ] M4 VM interpreter (malloc heap)
- [ ] M5 mark-and-sweep
- [ ] M6 stop-and-copy (Cheney)
- [ ] M7 stress mode, heap verifier, benchmarks

Run tests: `python3 tests/test_parser.py`
