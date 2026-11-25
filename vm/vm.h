#ifndef VM_H
#define VM_H

#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "opcodes.h"

typedef int64_t Value;      /* an int, a bool, or a reference (the address of an object) */
typedef uint64_t Word;

/* ---------- exit codes (section 9 of the specifications) ---------- */
#define EXIT_USAGE_ERROR   1
#define EXIT_RUNTIME_ERROR 100
#define EXIT_OUT_OF_MEMORY 101
#define EXIT_VERIFIER      102
#define EXIT_BAD_FILE      103

/* ---------- limits ---------- */
#define MAX_CALL_DEPTH    10000
#define VALUE_STACK_SLOTS (1 << 20)
#define MAX_LOCALS        64
#define MAX_STACK_DEPTH   64
#define MAX_FIELDS        64
#define HEADER_BYTES      16
#define DEFAULT_HEAP_BYTES (8u * 1024u * 1024u)
#define MIN_HEAP_BYTES    1024u

/* ---------- the program (what the loader reads from the .tbc file) ---------- */
enum { KIND_STRUCT = 1, KIND_ARRAY_VALUES = 2, KIND_ARRAY_REFERENCES = 3 };

typedef struct { uint8_t op; int32_t arg; } Instr;
typedef struct { uint8_t kind; uint32_t field_count; uint64_t pointer_mask; } TypeInfo;
typedef struct { uint32_t start, parameter_count, local_count; char *name; } Function;
typedef struct { uint32_t pc, depth; uint64_t locals_mask, stack_mask; } StackMap;

typedef struct {
    TypeInfo *types;        uint32_t type_count;
    Function *functions;    uint32_t function_count;
    uint32_t main_index;
    Instr *code;            uint32_t code_count;
    StackMap *maps;         uint32_t map_count;
    int32_t *map_at_pc;     /* for each instruction: index in `maps`, or -1 */
} Program;

int  load_program(const char *path, Program *program, char *error, size_t error_size);
void free_program(Program *program);

/* ---------- objects in the heap ----------
 *
 * Every block starts with a 16-byte header, followed by 8-byte slots.
 *   word 0:  bits 0-31   type_id (0 = a free block)
 *            bit  32     marked      (Mark-and-Sweep)
 *            bit  33     forwarded   (Stop-and-Copy)
 *            bits 34-63  size of the whole block, in 8-byte words
 *   word 1:  number of slots; when forwarded, the new address;
 *            in a free block, the address of the next free block
 */
#define MARK_BIT    ((Word)1 << 32)
#define FORWARD_BIT ((Word)1 << 33)
#define BLOCK_SHIFT 34

static inline Word *header_of(uint8_t *object) { return (Word *)object; }
static inline uint32_t object_type(uint8_t *object) { return (uint32_t)(header_of(object)[0] & 0xFFFFFFFFu); }
static inline size_t block_bytes(uint8_t *object) { return (size_t)(header_of(object)[0] >> BLOCK_SHIFT) * 8; }
static inline uint64_t object_slot_count(uint8_t *object) { return header_of(object)[1]; }
static inline Value *object_slots(uint8_t *object) { return (Value *)(object + HEADER_BYTES); }
static inline Word make_header(uint32_t type_id, size_t bytes) { return (Word)type_id | ((Word)(bytes / 8) << BLOCK_SHIFT); }

/* ---------- the heap and the two collectors ---------- */
enum { GC_MARK_SWEEP = 0, GC_COPY = 1 };

typedef struct {
    int algorithm;
    int stress;                 /* collect before every allocation */
    int verify;                 /* run the heap verifier after every collection */

    uint8_t *memory;            /* the whole heap (both semi-spaces for GC_COPY) */
    size_t total_bytes;

    Word free_head;             /* Mark-and-Sweep: address of the first free block, 0 if none */
    uint8_t **mark_stack;       /* Mark-and-Sweep: explicit stack, no recursion */
    size_t mark_top, mark_capacity;

    size_t half_bytes;          /* Stop-and-Copy: size of one semi-space */
    int current_space;          /* 0 or 1 */
    uint8_t *alloc_ptr, *alloc_limit;

    uint64_t collections, objects_allocated, bytes_allocated, bytes_reclaimed;
    double gc_seconds;
} Heap;

/* ---------- the running machine ---------- */
typedef struct {
    uint32_t function;
    uint32_t pc;                /* where this frame is suspended (a CALL), or where it allocates */
    Value *base;                /* its local variables; the operand stack follows them */
} Frame;

typedef struct {
    Program program;
    Heap heap;
    Value *stack, *stack_end, *sp;
    Frame *frames;
    uint32_t depth;             /* number of active frames */
} VM;

typedef void (*SlotVisitor)(Value *slot, void *context);

/* heap.c */
int      heap_init(Heap *heap, int algorithm, size_t total_bytes);
void     heap_free(Heap *heap);
uint8_t *heap_alloc(VM *vm, uint32_t type_id, uint64_t slot_count);
void     gc_collect(VM *vm);
void     for_each_root(VM *vm, SlotVisitor visit, void *context);
void     for_each_reference(const Program *program, uint8_t *object, SlotVisitor visit, void *context);
void     print_gc_stats(const Heap *heap);

/* verify.c */
void verify_heap(VM *vm);

/* interp.c */
int  run_program(VM *vm);

/* util: print a message on stderr (after flushing stdout) and exit */
void die(int code, const char *format, ...) __attribute__((noreturn, format(printf, 2, 3)));

#endif
