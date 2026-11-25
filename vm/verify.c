/* The heap verifier: after a collection, check that the heap and everything that points into it
 * is consistent. It is slow (it walks the whole heap), so it is only used with --verify or --stress. */
#include <stdarg.h>
#include <string.h>

#include "vm.h"

static void fail(const char *format, ...) __attribute__((noreturn, format(printf, 1, 2)));
static void fail(const char *format, ...) {
    fflush(stdout);
    fprintf(stderr, "heap verifier: ");
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fputc('\n', stderr);
    exit(EXIT_VERIFIER);
}

typedef struct {
    VM *vm;
    uint8_t *region_start, *region_end;     /* the part of the heap that holds live objects */
    uint8_t *starts;                        /* bitmap, one bit per 8 bytes of the heap: an object starts here */
    uint8_t *frees;                         /* same, for free blocks */
} Check;

static size_t unit_of(const Check *check, const uint8_t *address) {
    return (size_t)(address - check->vm->heap.memory) / 8;
}
static int get_bit(const uint8_t *bitmap, size_t index) { return (bitmap[index / 8] >> (index % 8)) & 1; }
static void set_bit(uint8_t *bitmap, size_t index) { bitmap[index / 8] |= (uint8_t)(1u << (index % 8)); }

/* one pass over the blocks of the region: check each header, remember where blocks start */
static size_t walk(Check *check, int free_blocks_allowed, int must_be_merged) {
    VM *vm = check->vm;
    const Program *program = &vm->program;
    size_t free_count = 0;
    int previous_was_free = 0;

    uint8_t *block = check->region_start;
    while (block < check->region_end) {
        Word first = header_of(block)[0];
        size_t size = block_bytes(block);
        uint32_t type = object_type(block);

        if (size < HEADER_BYTES || block + size > check->region_end)
            fail("block at offset %zu has an invalid size (%zu bytes)", (size_t)(block - vm->heap.memory), size);

        if (type == 0) {
            if (!free_blocks_allowed) fail("free block inside the live part of the heap");
            if (must_be_merged && previous_was_free) fail("two neighbouring free blocks were not merged");
            set_bit(check->frees, unit_of(check, block));
            free_count++;
            previous_was_free = 1;
        } else {
            previous_was_free = 0;
            if (type > program->type_count) fail("object with an unknown type_id %u", type);
            if (first & MARK_BIT) fail("object still marked after the collection");
            if (first & FORWARD_BIT) fail("live object marked as forwarded");
            const TypeInfo *info = &program->types[type - 1];
            uint64_t count = object_slot_count(block);
            if (count > size / 8 || HEADER_BYTES + count * 8 > size || size - (HEADER_BYTES + count * 8) >= HEADER_BYTES)
                fail("object of type %u: %" PRIu64 " slots do not fit a block of %zu bytes", type, count, size);
            if (info->kind == KIND_STRUCT && count != info->field_count)
                fail("struct object with %" PRIu64 " slots, its type has %u fields", count, info->field_count);
            if (info->kind != KIND_STRUCT && info->field_count != 0)
                fail("array type with fields");
            set_bit(check->starts, unit_of(check, block));
        }
        block += size;
    }
    if (block != check->region_end) fail("the blocks do not end exactly at the end of the region");
    return free_count;
}

static void check_slot(Value *slot, void *context) {
    Check *check = context;
    Value value = *slot;
    if (value == 0) return;
    uint8_t *address = (uint8_t *)(uintptr_t)value;
    if (((uintptr_t)address & 7) != 0 || address < check->region_start || address >= check->region_end)
        fail("a reference (0x%" PRIx64 ") points outside the live part of the heap", (uint64_t)value);
    if (!get_bit(check->starts, unit_of(check, address)))
        fail("a reference (0x%" PRIx64 ") does not point to the start of an object", (uint64_t)value);
}

/* the depth in a stack map must be what the stack really holds */
static void check_stack_maps(VM *vm) {
    const Program *program = &vm->program;
    for (uint32_t i = 0; i < vm->depth; i++) {
        const Frame *frame = &vm->frames[i];
        const Function *function = &program->functions[frame->function];
        const StackMap *map = &program->maps[program->map_at_pc[frame->pc]];
        const Value *operands = frame->base + function->local_count;
        const Value *top = (i + 1 < vm->depth) ? vm->frames[i + 1].base : vm->sp;
        if ((long)(top - operands) != (long)map->depth)
            fail("stack map of '%s' (instruction %u) says depth %u, the stack holds %ld values",
                 function->name, frame->pc, map->depth, (long)(top - operands));
    }
}

void verify_heap(VM *vm) {
    Heap *heap = &vm->heap;
    Check check;
    check.vm = vm;
    if (heap->algorithm == GC_MARK_SWEEP) {
        check.region_start = heap->memory;
        check.region_end = heap->memory + heap->total_bytes;
    } else {
        check.region_start = heap->memory + (size_t)heap->current_space * heap->half_bytes;
        check.region_end = heap->alloc_ptr;
        if (heap->alloc_ptr > heap->alloc_limit) fail("the allocation pointer is past the end of the semi-space");
    }

    size_t units = heap->total_bytes / 8 + 1;
    check.starts = calloc(units / 8 + 1, 1);
    check.frees = calloc(units / 8 + 1, 1);
    if (!check.starts || !check.frees) die(EXIT_OUT_OF_MEMORY, "out of memory in the heap verifier");

    int mark_sweep = heap->algorithm == GC_MARK_SWEEP;
    size_t free_blocks = walk(&check, mark_sweep, mark_sweep);

    if (mark_sweep) {                                         /* the free list lists every free block, once */
        size_t listed = 0;
        Word address = heap->free_head;
        while (address) {
            uint8_t *block = (uint8_t *)(uintptr_t)address;
            if (listed > free_blocks) fail("the free list is longer than the number of free blocks (a cycle?)");
            if (block < heap->memory || block >= heap->memory + heap->total_bytes || ((uintptr_t)block & 7) != 0 ||
                !get_bit(check.frees, unit_of(&check, block)))
                fail("the free list points to something that is not a free block");
            listed++;
            address = header_of(block)[1];
        }
        if (listed != free_blocks) fail("the free list has %zu blocks, the heap has %zu free blocks", listed, free_blocks);
    }

    for_each_root(vm, check_slot, &check);                    /* every root is null or a real object */
    for (uint8_t *block = check.region_start; block < check.region_end; block += block_bytes(block))
        if (object_type(block) != 0) for_each_reference(&vm->program, block, check_slot, &check);

    check_stack_maps(vm);
    free(check.starts);
    free(check.frees);
}
