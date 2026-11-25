/* gcvm: the Toy virtual machine.
 *
 *   gcvm <program.tbc> [--gc=ms|copy] [--heap=<bytes>] [--stress] [--verify] [--gc-stats]
 */
#include <errno.h>
#include <string.h>

#include "vm.h"

static void usage(void) {
    fprintf(stderr,
        "usage: gcvm <program.tbc> [options]\n"
        "  --gc=ms|copy      garbage collector: Mark-and-Sweep (default) or Stop-and-Copy\n"
        "  --heap=<bytes>    size of the heap (default %u, at least %u)\n"
        "  --stress          collect before every allocation (and verify the heap)\n"
        "  --verify          verify the heap after every collection\n"
        "  --gc-stats        print statistics about the collector on stderr at the end\n",
        DEFAULT_HEAP_BYTES, MIN_HEAP_BYTES);
}

int main(int argc, char **argv) {
    const char *path = NULL;
    int algorithm = GC_MARK_SWEEP, stress = 0, verify = 0, stats = 0;
    unsigned long long heap_bytes = DEFAULT_HEAP_BYTES;

    for (int i = 1; i < argc; i++) {
        const char *argument = argv[i];
        if (strcmp(argument, "--gc=ms") == 0) algorithm = GC_MARK_SWEEP;
        else if (strcmp(argument, "--gc=copy") == 0) algorithm = GC_COPY;
        else if (strncmp(argument, "--heap=", 7) == 0) {
            char *end = NULL;
            errno = 0;
            heap_bytes = strtoull(argument + 7, &end, 10);
            if (errno != 0 || end == argument + 7 || *end != '\0' ||
                heap_bytes < MIN_HEAP_BYTES || heap_bytes > 4294967296ULL) {
                fprintf(stderr, "gcvm: invalid heap size '%s' (from %u to 4294967296 bytes)\n", argument + 7, MIN_HEAP_BYTES);
                return EXIT_USAGE_ERROR;
            }
        }
        else if (strcmp(argument, "--stress") == 0) stress = 1;
        else if (strcmp(argument, "--verify") == 0) verify = 1;
        else if (strcmp(argument, "--gc-stats") == 0) stats = 1;
        else if (argument[0] == '-' || path != NULL) { usage(); return EXIT_USAGE_ERROR; }
        else path = argument;
    }
    if (!path) { usage(); return EXIT_USAGE_ERROR; }

    VM vm;
    memset(&vm, 0, sizeof vm);
    char error[256];
    if (load_program(path, &vm.program, error, sizeof error) != 0) {
        fprintf(stderr, "gcvm: %s: %s\n", path, error);
        return EXIT_BAD_FILE;
    }
    if (heap_init(&vm.heap, algorithm, (size_t)heap_bytes) != 0) die(EXIT_OUT_OF_MEMORY, "out of memory: cannot create the heap");
    vm.heap.stress = stress;
    vm.heap.verify = verify || stress;

    vm.stack = malloc(VALUE_STACK_SLOTS * sizeof(Value));
    vm.frames = malloc((MAX_CALL_DEPTH + 1) * sizeof(Frame));
    if (!vm.stack || !vm.frames) die(EXIT_OUT_OF_MEMORY, "out of memory: cannot create the stack");
    vm.stack_end = vm.stack + VALUE_STACK_SLOTS;
    vm.sp = vm.stack;

    static char output_buffer[1 << 16];
    setvbuf(stdout, output_buffer, _IOFBF, sizeof output_buffer);

    int code = run_program(&vm);

    fflush(stdout);
    if (stats) print_gc_stats(&vm.heap);
    free(vm.stack);
    free(vm.frames);
    heap_free(&vm.heap);
    free_program(&vm.program);
    return code;
}
