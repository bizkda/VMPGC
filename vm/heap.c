/* The heap, the allocator and the two garbage collectors.
 *
 * Both collectors are PRECISE: the roots are exactly the slots that the stack maps mark as
 * references, and inside an object only the fields that the type descriptor marks. A value
 * is never taken for a pointer because it looks like one. */
#include <stdarg.h>
#include <string.h>
#include <time.h>

#include "vm.h"

void die(int code, const char *format, ...) {
    fflush(stdout);
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fputc('\n', stderr);
    exit(code);
}

static double now_seconds(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

/* ---------------------------------------------------------------------
 *  creating and freeing the heap
 * --------------------------------------------------------------------- */
int heap_init(Heap *heap, int algorithm, size_t total_bytes) {
    memset(heap, 0, sizeof *heap);
    heap->algorithm = algorithm;
    total_bytes &= ~(size_t)15;
    heap->total_bytes = total_bytes;

    void *memory = NULL;
    if (posix_memalign(&memory, 16, total_bytes) != 0) return -1;
    heap->memory = memory;

    if (algorithm == GC_MARK_SWEEP) {
        /* at the start the whole heap is one free block */
        Word *header = (Word *)memory;
        header[0] = make_header(0, total_bytes);
        header[1] = 0;
        heap->free_head = (Word)(uintptr_t)memory;
    } else {
        heap->half_bytes = (total_bytes / 2) & ~(size_t)15;
        heap->current_space = 0;
        heap->alloc_ptr = heap->memory;
        heap->alloc_limit = heap->memory + heap->half_bytes;
    }
    return 0;
}

void heap_free(Heap *heap) {
    free(heap->memory);
    free(heap->mark_stack);
    memset(heap, 0, sizeof *heap);
}

/* ---------------------------------------------------------------------
 *  roots and references: what the GC is allowed to look at
 * --------------------------------------------------------------------- */
void for_each_root(VM *vm, SlotVisitor visit, void *context) {
    const Program *program = &vm->program;
    for (uint32_t i = 0; i < vm->depth; i++) {
        const Frame *frame = &vm->frames[i];
        int32_t map_index = program->map_at_pc[frame->pc];
        if (map_index < 0) die(EXIT_VERIFIER, "internal error: no stack map at instruction %u", frame->pc);
        const StackMap *map = &program->maps[map_index];
        const Function *function = &program->functions[frame->function];

        for (uint32_t k = 0; k < function->local_count; k++)
            if ((map->locals_mask >> k) & 1) visit(&frame->base[k], context);

        Value *operands = frame->base + function->local_count;
        for (uint32_t k = 0; k < map->depth; k++)
            if ((map->stack_mask >> k) & 1) visit(&operands[k], context);
    }
}

void for_each_reference(const Program *program, uint8_t *object, SlotVisitor visit, void *context) {
    const TypeInfo *type = &program->types[object_type(object) - 1];
    Value *slots = object_slots(object);
    uint64_t count = object_slot_count(object);

    if (type->kind == KIND_STRUCT) {
        for (uint64_t k = 0; k < count; k++)
            if ((type->pointer_mask >> k) & 1) visit(&slots[k], context);
    } else if (type->kind == KIND_ARRAY_REFERENCES) {
        for (uint64_t k = 0; k < count; k++) visit(&slots[k], context);
    }                                       /* an array of values has no references */
}

/* ---------------------------------------------------------------------
 *  Mark-and-Sweep
 * --------------------------------------------------------------------- */
static void mark_push(Heap *heap, uint8_t *object) {
    Word *header = header_of(object);
    if (header[0] & MARK_BIT) return;
    header[0] |= MARK_BIT;
    if (heap->mark_top == heap->mark_capacity) {
        size_t capacity = heap->mark_capacity ? heap->mark_capacity * 2 : 1024;
        uint8_t **stack = realloc(heap->mark_stack, capacity * sizeof *stack);
        if (!stack) die(EXIT_OUT_OF_MEMORY, "out of memory: cannot grow the mark stack");
        heap->mark_stack = stack;
        heap->mark_capacity = capacity;
    }
    heap->mark_stack[heap->mark_top++] = object;
}

static void mark_visit(Value *slot, void *context) {
    if (*slot != 0) mark_push((Heap *)context, (uint8_t *)(uintptr_t)*slot);
}

/* A free run becomes one free block, chained after `tail`; returns the new tail. */
static Word *close_run(Word *tail, uint8_t *start, size_t bytes) {
    header_of(start)[0] = make_header(0, bytes);
    header_of(start)[1] = 0;
    *tail = (Word)(uintptr_t)start;
    return &header_of(start)[1];
}

static void sweep(Heap *heap) {
    uint8_t *block = heap->memory;
    uint8_t *end = heap->memory + heap->total_bytes;
    uint8_t *run_start = NULL;
    size_t run_bytes = 0;
    Word *tail = &heap->free_head;
    heap->free_head = 0;

    while (block < end) {
        Word first = header_of(block)[0];
        size_t size = (size_t)(first >> BLOCK_SHIFT) * 8;
        if (size < HEADER_BYTES) die(EXIT_VERIFIER, "internal error: the heap is corrupted");
        int is_object = (first & 0xFFFFFFFFu) != 0;

        if (is_object && (first & MARK_BIT)) {
            header_of(block)[0] = first & ~MARK_BIT;          /* alive: keep it, clear the mark */
            if (run_start) {
                tail = close_run(tail, run_start, run_bytes);
                run_start = NULL;
                run_bytes = 0;
            }
        } else {                                              /* dead or already free: merge into a run */
            if (is_object) heap->bytes_reclaimed += size;
            if (!run_start) run_start = block;
            run_bytes += size;
        }
        block += size;
    }
    if (run_start) close_run(tail, run_start, run_bytes);
}

static void mark_sweep_collect(VM *vm) {
    Heap *heap = &vm->heap;
    heap->mark_top = 0;
    for_each_root(vm, mark_visit, heap);
    while (heap->mark_top > 0) {                              /* explicit stack: no recursion */
        uint8_t *object = heap->mark_stack[--heap->mark_top];
        for_each_reference(&vm->program, object, mark_visit, heap);
    }
    sweep(heap);
}

/* first fit in the free list; a block that is too big is split */
static uint8_t *mark_sweep_try_alloc(Heap *heap, size_t bytes, size_t *granted) {
    Word *link = &heap->free_head;
    while (*link) {
        uint8_t *block = (uint8_t *)(uintptr_t)*link;
        size_t block_size = block_bytes(block);
        Word next = header_of(block)[1];
        if (block_size >= bytes) {
            size_t rest = block_size - bytes;
            if (rest >= HEADER_BYTES) {
                uint8_t *remainder = block + bytes;
                header_of(remainder)[0] = make_header(0, rest);
                header_of(remainder)[1] = next;
                *link = (Word)(uintptr_t)remainder;
                *granted = bytes;
            } else {                                          /* too small to be a block: give it all */
                *link = next;
                *granted = block_size;
            }
            return block;
        }
        link = &header_of(block)[1];
    }
    return NULL;
}

/* ---------------------------------------------------------------------
 *  Stop-and-Copy (Cheney)
 * --------------------------------------------------------------------- */
typedef struct {
    uint8_t *free_ptr;          /* where the next copied object goes in the to-space */
} CopyState;

static void forward_visit(Value *slot, void *context) {
    CopyState *state = context;
    if (*slot == 0) return;
    uint8_t *object = (uint8_t *)(uintptr_t)*slot;
    Word *header = header_of(object);

    if (header[0] & FORWARD_BIT) {                            /* already copied: use the new address */
        *slot = (Value)header[1];
        return;
    }
    size_t size = block_bytes(object);
    uint8_t *copy = state->free_ptr;
    memcpy(copy, object, size);
    state->free_ptr += size;
    header[0] |= FORWARD_BIT;                                 /* leave a forwarding pointer behind */
    header[1] = (Word)(uintptr_t)copy;
    *slot = (Value)(uintptr_t)copy;
}

static void copy_collect(VM *vm) {
    Heap *heap = &vm->heap;
    uint8_t *from_start = heap->memory + (size_t)heap->current_space * heap->half_bytes;
    size_t used_before = (size_t)(heap->alloc_ptr - from_start);
    int to_space = 1 - heap->current_space;
    uint8_t *to_start = heap->memory + (size_t)to_space * heap->half_bytes;

    CopyState state = { to_start };
    for_each_root(vm, forward_visit, &state);                 /* roots are updated in place */

    uint8_t *scan = to_start;                                 /* Cheney's scan pointer */
    while (scan < state.free_ptr) {
        for_each_reference(&vm->program, scan, forward_visit, &state);
        scan += block_bytes(scan);
    }

    heap->bytes_reclaimed += used_before - (size_t)(state.free_ptr - to_start);
    heap->current_space = to_space;
    heap->alloc_ptr = state.free_ptr;
    heap->alloc_limit = to_start + heap->half_bytes;
}

/* ---------------------------------------------------------------------
 *  allocation
 * --------------------------------------------------------------------- */
void gc_collect(VM *vm) {
    Heap *heap = &vm->heap;
    double started = now_seconds();
    if (heap->algorithm == GC_MARK_SWEEP) mark_sweep_collect(vm);
    else copy_collect(vm);
    heap->collections++;
    heap->gc_seconds += now_seconds() - started;
    if (heap->verify) verify_heap(vm);
}

static uint8_t *try_alloc(Heap *heap, size_t bytes, size_t *granted) {
    if (heap->algorithm == GC_MARK_SWEEP) return mark_sweep_try_alloc(heap, bytes, granted);
    if ((size_t)(heap->alloc_limit - heap->alloc_ptr) >= bytes) {
        uint8_t *object = heap->alloc_ptr;
        heap->alloc_ptr += bytes;
        *granted = bytes;
        return object;
    }
    return NULL;
}

static void out_of_memory(const Heap *heap, uint64_t slot_count) {
    die(EXIT_OUT_OF_MEMORY, "out of memory: cannot allocate an object of %" PRIu64
        " slots in a heap of %zu bytes", slot_count, heap->total_bytes);
}

/* Allocate an object of `type_id` with `slot_count` slots, all zero (0, false or null).
 * The caller must have recorded its position (frame pc and vm->sp): the GC may run here. */
uint8_t *heap_alloc(VM *vm, uint32_t type_id, uint64_t slot_count) {
    Heap *heap = &vm->heap;
    if (slot_count > heap->total_bytes / 8) out_of_memory(heap, slot_count);
    size_t bytes = HEADER_BYTES + (size_t)slot_count * 8;

    if (heap->stress) gc_collect(vm);
    size_t granted = 0;
    uint8_t *object = try_alloc(heap, bytes, &granted);
    if (!object) {
        gc_collect(vm);
        object = try_alloc(heap, bytes, &granted);
        if (!object) out_of_memory(heap, slot_count);
    }

    header_of(object)[0] = make_header(type_id, granted);
    header_of(object)[1] = slot_count;
    memset(object + HEADER_BYTES, 0, granted - HEADER_BYTES);
    heap->objects_allocated++;
    heap->bytes_allocated += granted;
    return object;
}

void print_gc_stats(const Heap *heap) {
    fprintf(stderr, "[gc] algo=%s collectes=%" PRIu64 " objets_alloues=%" PRIu64
            " octets_alloues=%" PRIu64 " octets_recuperes=%" PRIu64 " temps_gc_ms=%.3f\n",
            heap->algorithm == GC_MARK_SWEEP ? "ms" : "copy", heap->collections,
            heap->objects_allocated, heap->bytes_allocated, heap->bytes_reclaimed,
            heap->gc_seconds * 1000.0);
}
