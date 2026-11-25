#!/usr/bin/env bash
# Guided demonstration of VMPGC.        Usage:  bash demo.sh      (or: make demo)
cd "$(dirname "$0")" || exit 1
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if [ -t 1 ]; then BOLD=$'\033[1m'; CYAN=$'\033[36m'; RESET=$'\033[0m'; else BOLD=""; CYAN=""; RESET=""; fi
title() { printf '\n%s== %s ==%s\n' "$BOLD" "$1" "$RESET"; }
say()   { printf '%s\n' "$1"; }
show()  { printf '%s$ %s%s\n' "$CYAN" "$*" "$RESET"; }

title "0. Build the virtual machine"
show make -C vm
make -s -C vm || exit 1

title "1. A Toy program: tests/list.toy"
say "It builds one list node a million times. Almost every node becomes garbage at once."
sed -n '1,22p' tests/list.toy

title "2. Compile it to bytecode (with the stack map the GC needs)"
show python3 compiler/toyc.py tests/list.toy -o "$work/list.tbc" --dump
python3 compiler/toyc.py tests/list.toy -o "$work/list.tbc" --dump | sed -n '1,22p'
say "..."
say "Look at the NEW instruction of push: the stack map says locals=0b101 (head and n are"
say "references, v is an int). That is how the collector knows what is a pointer."

title "3. Run it: a million nodes (32 MB) in a heap of 1 MB, with both collectors"
show ./vm/gcvm "$work/list.tbc" --gc=ms --heap=1048576 --gc-stats
./vm/gcvm "$work/list.tbc" --gc=ms --heap=1048576 --gc-stats
show ./vm/gcvm "$work/list.tbc" --gc=copy --heap=1048576 --gc-stats
./vm/gcvm "$work/list.tbc" --gc=copy --heap=1048576 --gc-stats

title "4. Cyclic garbage and a live ring, checked after every collection"
say "tests/programs/cycle.toy builds circular lists. --stress collects before every allocation"
say "and runs the heap verifier each time."
python3 compiler/toyc.py tests/programs/cycle.toy -o "$work/cycle.tbc"
show ./vm/gcvm "$work/cycle.tbc" --gc=ms --stress --gc-stats
./vm/gcvm "$work/cycle.tbc" --gc=ms --stress --gc-stats
show ./vm/gcvm "$work/cycle.tbc" --gc=copy --stress --gc-stats
./vm/gcvm "$work/cycle.tbc" --gc=copy --stress --gc-stats

title "5. References that only live on the operand stack"
say "In pair(mk(i), mk(i + 1)) the first object is only on the stack while the second is allocated."
say "A GC that missed it would free (or fail to move) a live object."
python3 compiler/toyc.py tests/programs/operand_stack_refs.toy -o "$work/stack.tbc"
show ./vm/gcvm "$work/stack.tbc" --gc=copy --stress
./vm/gcvm "$work/stack.tbc" --gc=copy --stress
say "(expected: 4000000 and 12250)"

title "6. Errors are reported, not crashes"
python3 compiler/toyc.py tests/programs/err_index.toy -o "$work/err.tbc"
show ./vm/gcvm "$work/err.tbc"
./vm/gcvm "$work/err.tbc"; echo "exit code: $?"
python3 compiler/toyc.py tests/programs/err_oom.toy -o "$work/oom.tbc"
show ./vm/gcvm "$work/oom.tbc" --heap=65536
./vm/gcvm "$work/oom.tbc" --heap=65536; echo "exit code: $?"
show python3 compiler/toyc.py tests/programs/bad_type.toy
python3 compiler/toyc.py tests/programs/bad_type.toy -o "$work/bad.tbc"; echo "exit code: $?"

title "7. All the tests"
show python3 tests/run_all.py
python3 tests/run_all.py
