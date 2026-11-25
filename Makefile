# VMPGC: a compiler (Python) and a virtual machine (C) with a precise garbage collector.
#
#   make              build the virtual machine (vm/gcvm)
#   make test         run every test
#   make test-asan    the same, with AddressSanitizer and UndefinedBehaviorSanitizer
#   make demo         guided demonstration
#   make bench        compare the two garbage collectors
#   make clean

PYTHON ?= python3

.PHONY: all vm debug test test-asan demo bench clean

all: vm

vm:
	$(MAKE) -s -C vm

debug:
	$(MAKE) -s -C vm debug

test: vm
	$(PYTHON) tests/run_all.py

test-asan: debug
	$(PYTHON) tests/run_all.py --asan

demo: vm
	bash demo.sh

bench: vm
	$(PYTHON) tests/benchmark.py --output docs/benchmark.md

clean:
	$(MAKE) -s -C vm clean
	find . -name __pycache__ -prune -exec rm -rf {} +
	rm -f tests/*.tbc
