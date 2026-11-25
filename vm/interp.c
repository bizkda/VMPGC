/* The interpreter: runs the bytecode of a loaded program.
 *
 * The machine has one big stack of 64-bit values. A function call gets a frame: its local
 * variables (the arguments are the first ones, they were just pushed by the caller) and, right
 * after them, its operand stack. */
#include <stdarg.h>
#include <string.h>

#include "vm.h"

static void runtime_error(VM *vm, const char *format, ...) __attribute__((noreturn, format(printf, 2, 3)));
static void runtime_error(VM *vm, const char *format, ...) {
    fflush(stdout);
    const Frame *frame = &vm->frames[vm->depth - 1];
    fprintf(stderr, "runtime error: ");
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fprintf(stderr, "\n  in function '%s', instruction %u\n",
            vm->program.functions[frame->function].name, frame->pc);
    exit(EXIT_RUNTIME_ERROR);
}

/* 64-bit arithmetic that wraps around (done on unsigned values: signed overflow is undefined in C) */
static inline Value wrap_add(Value a, Value b) { return (Value)((uint64_t)a + (uint64_t)b); }
static inline Value wrap_sub(Value a, Value b) { return (Value)((uint64_t)a - (uint64_t)b); }
static inline Value wrap_mul(Value a, Value b) { return (Value)((uint64_t)a * (uint64_t)b); }
static inline Value wrap_neg(Value a) { return (Value)(0 - (uint64_t)a); }

int run_program(VM *vm) {
    const Program *program = &vm->program;
    const Instr *code = program->code;
    const Function *main_function = &program->functions[program->main_index];

    /* the frame of main */
    vm->depth = 1;
    Frame *frame = &vm->frames[0];
    frame->function = program->main_index;
    frame->pc = main_function->start;
    frame->base = vm->stack;
    Value *base = vm->stack;
    for (uint32_t k = 0; k < main_function->local_count; k++) base[k] = 0;
    Value *sp = base + main_function->local_count;
    uint32_t pc = main_function->start;

    /* tell the VM where we are: needed before anything that can stop the program or run the GC */
#define SYNC() do { frame->pc = pc; vm->sp = sp; } while (0)
#define ERROR(...) do { SYNC(); runtime_error(vm, __VA_ARGS__); } while (0)
#define PUSH(value) do { if (sp >= vm->stack_end) ERROR("stack overflow (the value stack is full)"); *sp++ = (value); } while (0)

    for (;;) {
        const Instr instruction = code[pc];
        switch (instruction.op) {
        case OP_PUSH_INT:   PUSH((Value)instruction.arg); pc++; break;
        case OP_PUSH_NULL:  PUSH(0); pc++; break;
        case OP_POP:        sp--; pc++; break;
        case OP_LOAD_LOCAL: PUSH(base[instruction.arg]); pc++; break;
        case OP_STORE_LOCAL: base[instruction.arg] = *--sp; pc++; break;

        case OP_ADD: sp--; sp[-1] = wrap_add(sp[-1], sp[0]); pc++; break;
        case OP_SUB: sp--; sp[-1] = wrap_sub(sp[-1], sp[0]); pc++; break;
        case OP_MUL: sp--; sp[-1] = wrap_mul(sp[-1], sp[0]); pc++; break;
        case OP_DIV: {
            Value b = sp[-1], a = sp[-2];
            if (b == 0) ERROR("division by zero");
            sp--;
            sp[-1] = (b == -1) ? wrap_neg(a) : a / b;       /* INT64_MIN / -1 would overflow */
            pc++;
            break;
        }
        case OP_MOD: {
            Value b = sp[-1], a = sp[-2];
            if (b == 0) ERROR("modulo by zero");
            sp--;
            sp[-1] = (b == -1) ? 0 : a % b;
            pc++;
            break;
        }
        case OP_NEG: sp[-1] = wrap_neg(sp[-1]); pc++; break;
        case OP_NOT: sp[-1] = (sp[-1] == 0); pc++; break;

        case OP_EQ: sp--; sp[-1] = (sp[-1] == sp[0]); pc++; break;
        case OP_NE: sp--; sp[-1] = (sp[-1] != sp[0]); pc++; break;
        case OP_LT: sp--; sp[-1] = (sp[-1] <  sp[0]); pc++; break;
        case OP_LE: sp--; sp[-1] = (sp[-1] <= sp[0]); pc++; break;
        case OP_GT: sp--; sp[-1] = (sp[-1] >  sp[0]); pc++; break;
        case OP_GE: sp--; sp[-1] = (sp[-1] >= sp[0]); pc++; break;

        case OP_JMP: pc = (uint32_t)instruction.arg; break;
        case OP_JZ: {
            Value condition = *--sp;
            pc = (condition == 0) ? (uint32_t)instruction.arg : pc + 1;
            break;
        }

        case OP_CALL: {
            const Function *callee = &program->functions[instruction.arg];
            if (vm->depth >= MAX_CALL_DEPTH) ERROR("stack overflow (more than %d nested calls)", MAX_CALL_DEPTH);
            Value *new_base = sp - callee->parameter_count;    /* the arguments become the first locals */
            if (new_base + callee->local_count >= vm->stack_end) ERROR("stack overflow (the value stack is full)");
            frame->pc = pc;                                    /* this frame stays suspended on the CALL */
            for (uint32_t k = callee->parameter_count; k < callee->local_count; k++) new_base[k] = 0;
            sp = new_base + callee->local_count;
            frame = &vm->frames[vm->depth++];
            frame->function = (uint32_t)instruction.arg;
            frame->base = new_base;
            frame->pc = callee->start;
            base = new_base;
            pc = callee->start;
            break;
        }
        case OP_RET: {
            Value result = sp[-1];
            if (vm->depth == 1) return (int)(result & 0xFF);   /* main returned: the program ends */
            sp = base;                                         /* drop the callee's frame */
            vm->depth--;
            frame = &vm->frames[vm->depth - 1];
            base = frame->base;
            *sp++ = result;
            pc = frame->pc + 1;                                /* continue after the CALL */
            break;
        }

        case OP_NEW: {
            SYNC();
            uint8_t *object = heap_alloc(vm, (uint32_t)instruction.arg,
                                         program->types[instruction.arg - 1].field_count);
            PUSH((Value)(uintptr_t)object);
            pc++;
            break;
        }
        case OP_NEW_ARRAY: {
            Value length = sp[-1];
            if (length < 0) ERROR("negative array size (%" PRId64 ")", length);
            sp--;                                              /* the size is gone before the allocation */
            SYNC();
            uint8_t *array = heap_alloc(vm, (uint32_t)instruction.arg, (uint64_t)length);
            PUSH((Value)(uintptr_t)array);
            pc++;
            break;
        }
        case OP_GETFIELD: {
            if (sp[-1] == 0) ERROR("null reference (reading a field)");
            uint8_t *object = (uint8_t *)(uintptr_t)sp[-1];
            if ((uint64_t)instruction.arg >= object_slot_count(object)) ERROR("field %d does not exist", instruction.arg);
            sp[-1] = object_slots(object)[instruction.arg];
            pc++;
            break;
        }
        case OP_PUTFIELD: {
            if (sp[-2] == 0) ERROR("null reference (writing a field)");
            uint8_t *object = (uint8_t *)(uintptr_t)sp[-2];
            if ((uint64_t)instruction.arg >= object_slot_count(object)) ERROR("field %d does not exist", instruction.arg);
            object_slots(object)[instruction.arg] = sp[-1];
            sp -= 2;
            pc++;
            break;
        }
        case OP_ALOAD: {
            if (sp[-2] == 0) ERROR("null reference (reading an array element)");
            uint8_t *array = (uint8_t *)(uintptr_t)sp[-2];
            Value index = sp[-1];
            if (index < 0 || (uint64_t)index >= object_slot_count(array))
                ERROR("index %" PRId64 " is out of bounds for an array of length %" PRIu64, index, object_slot_count(array));
            sp--;
            sp[-1] = object_slots(array)[index];
            pc++;
            break;
        }
        case OP_ASTORE: {
            if (sp[-3] == 0) ERROR("null reference (writing an array element)");
            uint8_t *array = (uint8_t *)(uintptr_t)sp[-3];
            Value index = sp[-2];
            if (index < 0 || (uint64_t)index >= object_slot_count(array))
                ERROR("index %" PRId64 " is out of bounds for an array of length %" PRIu64, index, object_slot_count(array));
            object_slots(array)[index] = sp[-1];
            sp -= 3;
            pc++;
            break;
        }

        case OP_PRINT_INT:  printf("%" PRId64 "\n", *--sp); pc++; break;
        case OP_PRINT_BOOL: fputs(*--sp ? "true\n" : "false\n", stdout); pc++; break;

        default: ERROR("invalid instruction");
        }
    }
#undef SYNC
#undef ERROR
#undef PUSH
}
