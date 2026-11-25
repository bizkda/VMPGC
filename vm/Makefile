# The Toy virtual machine.
#   make          build gcvm
#   make debug    build gcvm_asan, with AddressSanitizer and UndefinedBehaviorSanitizer
#   make clean

CC       ?= gcc
CFLAGS   ?= -std=gnu11 -O2 -Wall -Wextra -Wpedantic
SOURCES  := main.c loader.c heap.c verify.c interp.c
HEADERS  := vm.h opcodes.h

gcvm: $(SOURCES) $(HEADERS)
	$(CC) $(CFLAGS) -o $@ $(SOURCES)

debug: gcvm_asan

gcvm_asan: $(SOURCES) $(HEADERS)
	$(CC) -std=gnu11 -O1 -g -Wall -Wextra -fsanitize=address,undefined -fno-sanitize-recover=undefined \
	      -fno-omit-frame-pointer -o $@ $(SOURCES)

clean:
	rm -f gcvm gcvm_asan

.PHONY: debug clean
